import asyncio
import inspect
import logging
import threading
import time
import typing
import warnings
from asyncio import Future, AbstractEventLoop, Task  # noqa
from asyncio.events import get_event_loop
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from functools import partial, wraps
from multiprocessing import cpu_count
from types import MappingProxyType
from typing import NamedTuple, Any, Optional, TypeVar, Callable  # noqa

from .iterator_wrapper import IteratorWrapper

T = typing.TypeVar('T')
F = TypeVar('F', bound=Callable[..., Any])

try:
    from queue import SimpleQueue
except ImportError:
    from queue import Queue as SimpleQueue  # type: ignore

log = logging.getLogger(__name__)


class ThreadPoolException(RuntimeError):
    pass


try:
    import contextvars

    def context_partial(func: F, *args: Any, **kwargs: Any) -> Any:
        context = contextvars.copy_context()
        return partial(context.run, func, *args, **kwargs)

except ImportError:
    context_partial = partial

WorkItemBase = NamedTuple(
    "WorkItemBase", (
        ("func", typing.Callable[..., Any]),
        ("args", typing.Tuple[Any, ...]),
        ("kwargs", typing.Dict[str, Any]),
        ("future", asyncio.Future),
        ("loop", asyncio.AbstractEventLoop),
    ),
)


class WorkItem(WorkItemBase):
    @staticmethod
    def set_result(
        future: Future, result: Any, exception: Exception
    ) -> None:
        if future.done():
            return

        if exception:
            future.set_exception(exception)
        else:
            future.set_result(result)

    def __call__(self) -> None:
        if self.future.done():
            return

        result, exception = None, None

        if self.loop.is_closed():
            raise asyncio.CancelledError

        try:
            result = self.func(*self.args, **self.kwargs)
        except Exception as e:
            exception = e

        if self.loop.is_closed():
            raise asyncio.CancelledError

        self.loop.call_soon_threadsafe(
            self.__class__.set_result,
            self.future,
            result,
            exception,
        )


class ThreadPoolExecutor(ThreadPoolExecutorBase):
    __slots__ = (
        "__futures", "__pool", "__tasks",
        "__write_lock", "__thread_events",
    )

    def __init__(
        self,
        max_workers: int = max((cpu_count(), 4)),
        loop: AbstractEventLoop = None
    ) -> None:
        if loop:
            warnings.warn(DeprecationWarning("loop argument is obsolete"))

        self.__futures = set()  # type: typing.Set[Future[Any]]

        self.__thread_events = set()  # type: typing.Set[threading.Event]
        self.__tasks = SimpleQueue()  # type: SimpleQueue[Optional[WorkItem]]
        self.__write_lock = threading.RLock()

        pools = set()
        for idx in range(max_workers):
            pools.add(self._start_thread(idx))

        self.__pool = frozenset(
            pools)  # type: typing.FrozenSet[threading.Thread]

    def _start_thread(self, idx: int) -> threading.Thread:
        event = threading.Event()
        self.__thread_events.add(event)

        thread = threading.Thread(
            target=self._in_thread,
            name="[%d] Thread Pool" % idx,
            args=(event,),
        )

        thread.daemon = True
        thread.start()
        return thread

    def _in_thread(self, event: threading.Event) -> None:
        while True:
            work_item = self.__tasks.get()

            if work_item is None:
                break

            try:
                if work_item.loop.is_closed():
                    log.warning(
                        "Event loop is closed. Call %r skipped",
                        work_item.func,
                    )
                    continue

                work_item()
            except asyncio.CancelledError:
                break
            finally:
                del work_item

        event.set()

    def submit(  # type: ignore
        self, fn: F, *args: Any, **kwargs: Any
    ) -> Future:

        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        loop = asyncio.get_event_loop()

        with self.__write_lock:
            future = loop.create_future()  # type: asyncio.Future[Any]
            self.__futures.add(future)
            future.add_done_callback(self.__futures.remove)

            self.__tasks.put_nowait(
                WorkItem(
                    func=fn,
                    args=args,
                    kwargs=kwargs,
                    future=future,
                    loop=loop,
                ),
            )

            return future

    def shutdown(self, wait: bool = True) -> None:
        for _ in self.__pool:
            self.__tasks.put_nowait(None)

        for f in filter(lambda x: not x.done(), self.__futures):
            f.set_exception(ThreadPoolException("Pool closed"))

        if not wait:
            return

        while not all(e.is_set() for e in self.__thread_events):
            time.sleep(0)

    def _adjust_thread_count(self) -> None:
        raise NotImplementedError

    def __del__(self) -> None:
        self.shutdown()


def run_in_executor(
    func: F,
    executor: ThreadPoolExecutorBase = None,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
) -> Future:
    loop = get_event_loop()
    # noinspection PyTypeChecker
    return loop.run_in_executor(  # type: ignore
        executor, context_partial(func, *args, **kwargs),
    )


async def _awaiter(future: Future) -> T:
    try:
        result = await future
        return result
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


def threaded(func: F) -> Callable[..., typing.Awaitable[Any]]:
    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> typing.Awaitable[Any]:
        future = run_in_executor(func=func, args=args, kwargs=kwargs)
        result = _awaiter(future)  # type: Any
        return result

    return wrap


def run_in_new_thread(
    func: F,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
    detouch: bool = True,
    no_return: bool = False,
) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    def set_result(result: Any) -> None:
        if future.done() or loop.is_closed():
            return

        future.set_result(result)

    def set_exception(exc: Exception) -> None:
        if future.done() or loop.is_closed():
            return

        future.set_exception(exc)

    @wraps(func)
    def in_thread(target: F) -> None:
        try:
            loop.call_soon_threadsafe(
                set_result, target(),
            )
        except Exception as exc:
            if loop.is_closed() and no_return:
                return

            elif loop.is_closed():
                log.exception("Uncaught exception from separate thread")
                return

            loop.call_soon_threadsafe(set_exception, exc)

    thread = threading.Thread(
        target=in_thread, name=func.__name__,
        args=(
            context_partial(func, *args, **kwargs),
        ),
    )

    thread.daemon = detouch

    thread.start()
    return future


def threaded_separate(
    func: F,
    detouch: bool = True
) -> Callable[..., typing.Awaitable[Any]]:
    if isinstance(func, bool):
        return partial(threaded_separate, detouch=detouch)

    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        future = run_in_new_thread(
            func, args=args, kwargs=kwargs, detouch=detouch,
        )

        return _awaiter(future)

    return wrap


def threaded_iterable(
    func: F = None,
    max_size: int = 0
) -> Any:
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        return IteratorWrapper(
            context_partial(func, *args, **kwargs),  # type: ignore
            max_size=max_size,
        )

    return wrap


class IteratorWrapperSeparate(IteratorWrapper):
    @threaded_separate
    def _run(self) -> None:
        return self._in_thread()


def threaded_iterable_separate(func: F = None, max_size: int = 0) -> Any:
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        return IteratorWrapperSeparate(
            context_partial(func, *args, **kwargs),  # type: ignore
            max_size=max_size,
        )

    return wrap


class CoroutineWaiter:
    def __init__(
        self,
        loop: asyncio.AbstractEventLoop,
        coroutine_func: F,
        *args: Any,
        **kwargs: Any
    ):
        self.__func = partial(
            coroutine_func, *args, **kwargs
        )  # type: partial[Any]
        self.__loop = loop
        self.__event = threading.Event()
        self.__result = None
        self.__exception = None  # type: Optional[BaseException]

    def _on_result(self, task: asyncio.Task) -> None:
        self.__exception = task.exception()
        if self.__exception is None:
            self.__result = task.result()
        self.__event.set()

    def _awaiter(self) -> None:
        task = self.__loop.create_task(self.__func())  # type: Task[Any]
        task.add_done_callback(self._on_result)

    def start(self) -> None:
        self.__loop.call_soon_threadsafe(self._awaiter)

    def wait(self) -> Any:
        self.__event.wait()
        if self.__exception is not None:
            raise self.__exception
        return self.__result


def sync_wait_coroutine(
    loop: AbstractEventLoop,
    coro_func: F,
    *args: Any,
    **kwargs: Any
) -> Any:
    waiter = CoroutineWaiter(loop, coro_func, *args, **kwargs)
    waiter.start()
    return waiter.wait()
