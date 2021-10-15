import asyncio
import inspect
import logging
import threading
import time
import typing
import warnings
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from functools import partial, wraps
from multiprocessing import cpu_count
from types import MappingProxyType

from .counters import Statistic
from .iterator_wrapper import IteratorWrapper


if not hasattr(asyncio, "get_running_loop"):
    def get_running_loop() -> asyncio.AbstractEventLoop:
        loop = asyncio.get_event_loop()
        if not loop.is_running():
            raise RuntimeError("no running event loop")
        return loop
else:
    get_running_loop = asyncio.get_running_loop


T = typing.TypeVar("T")
F = typing.TypeVar("F", bound=typing.Callable[..., typing.Any])

try:
    from queue import SimpleQueue
except ImportError:
    from queue import Queue as SimpleQueue  # type: ignore

log = logging.getLogger(__name__)


class ThreadPoolException(RuntimeError):
    pass


try:
    import contextvars

    def context_partial(
        func: F, *args: typing.Any,
        **kwargs: typing.Any
    ) -> typing.Any:
        context = contextvars.copy_context()
        return partial(context.run, func, *args, **kwargs)

except ImportError:
    context_partial = partial


class WorkItemBase(typing.NamedTuple):
    func: typing.Callable[..., typing.Any]
    args: typing.Tuple[typing.Any, ...]
    kwargs: typing.Dict[str, typing.Any]
    future: asyncio.Future
    loop: asyncio.AbstractEventLoop


class ThreadPoolStatistic(Statistic):
    threads: int
    done: int
    error: int
    success: int
    submitted: int
    sum_time: float


class WorkItem(WorkItemBase):
    @staticmethod
    def set_result(
        future: asyncio.Future, result: typing.Any, exception: Exception,
    ) -> None:
        if future.done():
            return

        if exception:
            future.set_exception(exception)
        else:
            future.set_result(result)

    def __call__(self, statistic: ThreadPoolStatistic) -> None:
        if self.future.done():
            return

        result, exception = None, None

        delta = -self.loop.time()
        try:
            result = self.func(*self.args, **self.kwargs)
            statistic.success += 1
        except BaseException as e:
            statistic.error += 1
            exception = e
        finally:
            delta += time.monotonic()
            statistic.sum_time += delta
            statistic.done += 1

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
        self, max_workers: int = max((cpu_count(), 4)),
        loop: asyncio.AbstractEventLoop = None,
        statistic_name: typing.Optional[str] = None,
    ) -> None:
        """"""
        if loop:
            warnings.warn(DeprecationWarning("loop argument is obsolete"))

        self.__futures: typing.Set[asyncio.Future[typing.Any]] = set()

        self.__thread_events: typing.Set[threading.Event] = set()
        self.__tasks: SimpleQueue[typing.Optional[WorkItem]] = SimpleQueue()
        self.__write_lock = threading.RLock()
        self._statistic = ThreadPoolStatistic(statistic_name)

        pools = set()
        for idx in range(max_workers):
            pools.add(self._start_thread(idx))

        self.__pool = frozenset(
            pools,
        )  # type: typing.FrozenSet[threading.Thread]

    def _start_thread(self, idx: int) -> threading.Thread:
        event = threading.Event()
        self.__thread_events.add(event)

        thread_name = "Thread {}".format(idx)

        if self._statistic.name:
            thread_name += " from pool {}".format(self._statistic.name)

        thread = threading.Thread(
            target=self._in_thread,
            name=thread_name.strip(),
            args=(event,),
        )

        thread.daemon = True
        thread.start()
        return thread

    def _in_thread(self, event: threading.Event) -> None:
        self._statistic.threads += 1

        try:
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

                    work_item(self._statistic)
                finally:
                    del work_item
        finally:
            self._statistic.threads -= 1
            event.set()

    def submit(  # type: ignore
        self, fn: F, *args: typing.Any, **kwargs: typing.Any
    ) -> asyncio.Future:
        """
        Submit blocking function to the pool
        """
        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)

        with self.__write_lock:
            self.__tasks.put_nowait(
                WorkItem(
                    func=fn,
                    args=args,
                    kwargs=kwargs,
                    future=future,
                    loop=loop,
                ),
            )

        self._statistic.submitted += 1
        return future

    # noinspection PyMethodOverriding
    def shutdown(self, wait: bool = True) -> None:  # type: ignore
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
    func: typing.Callable[..., T],
    executor: ThreadPoolExecutorBase = None,
    args: typing.Any = (),
    kwargs: typing.Any = MappingProxyType({}),
) -> typing.Awaitable[T]:
    try:
        loop = get_running_loop()
        return loop.run_in_executor(
            executor, context_partial(func, *args, **kwargs),
        )
    except RuntimeError:
        # In case the event loop is not running right now is
        # returning coroutine to avoid DeprecationWarning in Python 3.10
        async def lazy_wrapper() -> T:
            loop = get_running_loop()
            return await loop.run_in_executor(
                executor, context_partial(func, *args, **kwargs),
            )
        return lazy_wrapper()


async def _awaiter(future: asyncio.Future) -> T:
    try:
        result = await future
        return result
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


def threaded(
    func: typing.Callable[..., T],
) -> typing.Callable[..., typing.Awaitable[T]]:
    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    @wraps(func)
    def wrap(
        *args: typing.Any, **kwargs: typing.Any
    ) -> typing.Awaitable[T]:
        return run_in_executor(func=func, args=args, kwargs=kwargs)

    return wrap


def run_in_new_thread(
    func: F,
    args: typing.Any = (),
    kwargs: typing.Any = MappingProxyType({}),
    detach: bool = True,
    no_return: bool = False,
    statistic_name: typing.Optional[str] = None,
) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    statistic = ThreadPoolStatistic(statistic_name)

    def set_result(result: typing.Any) -> None:
        if future.done() or loop.is_closed():
            return

        future.set_result(result)

    def set_exception(exc: Exception) -> None:
        if future.done() or loop.is_closed():
            return

        future.set_exception(exc)

    @wraps(func)
    def in_thread(target: F) -> None:
        statistic.threads += 1
        statistic.submitted += 1

        try:
            loop.call_soon_threadsafe(
                set_result, target(),
            )
            statistic.success += 1
        except Exception as exc:
            statistic.error += 1
            if loop.is_closed() and no_return:
                return

            elif loop.is_closed():
                log.exception("Uncaught exception from separate thread")
                return

            loop.call_soon_threadsafe(set_exception, exc)
        finally:
            statistic.done += 1
            statistic.threads -= 1

    thread = threading.Thread(
        target=in_thread, name=func.__name__,
        args=(
            context_partial(func, *args, **kwargs),
        ),
    )

    thread.daemon = detach

    thread.start()
    return future


def threaded_separate(
    func: F,
    detach: bool = True,
) -> typing.Callable[..., typing.Awaitable[typing.Any]]:
    if isinstance(func, bool):
        return partial(threaded_separate, detach=detach)

    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    @wraps(func)
    def wrap(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        future = run_in_new_thread(
            func, args=args, kwargs=kwargs, detach=detach,
        )

        return _awaiter(future)

    return wrap


def threaded_iterable(
    func: F = None,
    max_size: int = 0,
) -> typing.Any:
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
        return IteratorWrapper(
            context_partial(func, *args, **kwargs),  # type: ignore
            max_size=max_size,
        )

    return wrap


class IteratorWrapperSeparate(IteratorWrapper):
    async def _run(self) -> typing.Any:
        return await run_in_new_thread(self._in_thread)


def threaded_iterable_separate(func: F = None, max_size: int = 0) -> typing.Any:
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args: typing.Any, **kwargs: typing.Any) -> typing.Any:
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
        *args: typing.Any,
        **kwargs: typing.Any
    ):
        self.__func: typing.Callable[..., typing.Any] = partial(
            coroutine_func, *args, **kwargs
        )
        self.__loop = loop
        self.__event = threading.Event()
        self.__result = None
        self.__exception: typing.Optional[BaseException] = None

    def _on_result(self, task: asyncio.Task) -> None:
        self.__exception = task.exception()
        if self.__exception is None:
            self.__result = task.result()
        self.__event.set()

    def _awaiter(self) -> None:
        task: asyncio.Task = self.__loop.create_task(self.__func())
        task.add_done_callback(self._on_result)

    def start(self) -> None:
        self.__loop.call_soon_threadsafe(self._awaiter)

    def wait(self) -> typing.Any:
        self.__event.wait()
        if self.__exception is not None:
            raise self.__exception
        return self.__result


def sync_wait_coroutine(
    loop: asyncio.AbstractEventLoop,
    coro_func: F,
    *args: typing.Any,
    **kwargs: typing.Any
) -> typing.Any:
    waiter = CoroutineWaiter(loop, coro_func, *args, **kwargs)
    waiter.start()
    return waiter.wait()
