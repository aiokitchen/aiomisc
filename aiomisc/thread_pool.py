import asyncio
import inspect
import logging
import threading
import time
import typing
import warnings
from asyncio.events import get_event_loop
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from functools import partial, wraps
from multiprocessing import cpu_count
from types import MappingProxyType
from typing import NamedTuple

from .iterator_wrapper import IteratorWrapper


try:
    from queue import SimpleQueue
except ImportError:
    from queue import Queue as SimpleQueue


log = logging.getLogger(__name__)


class ThreadPoolException(RuntimeError):
    pass


try:
    import contextvars

    def context_partial(func, *args, **kwargs):
        context = contextvars.copy_context()
        return partial(context.run, func, *args, **kwargs)

except ImportError:
    context_partial = partial


WorkItemBase = NamedTuple(
    "WorkItemBase", (
        ("func", typing.Callable),
        ("args", typing.Tuple),
        ("kwargs", typing.Dict),
        ("future", asyncio.Future),
        ("loop", asyncio.AbstractEventLoop),
    ),
)


class WorkItem(WorkItemBase):
    @staticmethod
    def set_result(future, result, exception):
        if future.done():
            return

        if exception:
            future.set_exception(exception)
        else:
            future.set_result(result)

    def __call__(self):
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

    def __init__(self, max_workers=max((cpu_count(), 4)), loop=None):
        if loop:
            warnings.warn(DeprecationWarning("loop argument is obsolete"))

        self.__futures = set()

        self.__pool = set()
        self.__thread_events = set()
        self.__tasks = SimpleQueue()
        self.__write_lock = threading.RLock()

        for idx in range(max_workers):
            self.__pool.add(self._start_thread(idx))

        self.__pool = frozenset(self.__pool)

    def _start_thread(self, idx):
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

    def _in_thread(self, event: threading.Event):
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

    def submit(self, fn, *args, **kwargs):
        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        loop = asyncio.get_event_loop()

        with self.__write_lock:
            future = loop.create_future()     # type: asyncio.Future
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

    def shutdown(self, wait=True):
        for _ in self.__pool:
            self.__tasks.put_nowait(None)

        for f in filter(lambda x: not x.done(), self.__futures):
            f.set_exception(ThreadPoolException("Pool closed"))

        if not wait:
            return

        while not all(e.is_set() for e in self.__thread_events):
            time.sleep(0)

    def _adjust_thread_count(self):
        raise NotImplementedError

    def __del__(self):
        self.shutdown()


def run_in_executor(
    func, executor=None, args=(),
    kwargs=MappingProxyType({}),
) -> asyncio.Future:

    loop = get_event_loop()
    # noinspection PyTypeChecker
    return loop.run_in_executor(
        executor, context_partial(func, *args, **kwargs),
    )


async def _awaiter(future):
    try:
        result = await future
        return result
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


def threaded(func):
    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    @wraps(func)
    def wrap(*args, **kwargs):
        future = run_in_executor(func=func, args=args, kwargs=kwargs)
        result = _awaiter(future)
        return result

    return wrap


def run_in_new_thread(
    func, args=(), kwargs=MappingProxyType({}),
    detouch=True, no_return=False,
) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    def set_result(result):
        if future.done() or loop.is_closed():
            return

        future.set_result(result)

    def set_exception(exc):
        if future.done() or loop.is_closed():
            return

        future.set_exception(exc)

    @wraps(func)
    def in_thread(target):
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


def threaded_separate(func, detouch=True):
    if isinstance(func, bool):
        return partial(threaded_separate, detouch=detouch)

    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    @wraps(func)
    def wrap(*args, **kwargs):
        future = run_in_new_thread(
            func, args=args, kwargs=kwargs, detouch=detouch,
        )

        return _awaiter(future)

    return wrap


def threaded_iterable(func=None, max_size: int = 0):
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args, **kwargs):
        return IteratorWrapper(
            context_partial(func, *args, **kwargs),
            max_size=max_size,
        )

    return wrap


class IteratorWrapperSeparate(IteratorWrapper):
    @threaded_separate
    def _run(self):
        return self._in_thread()


def threaded_iterable_separate(func=None, max_size: int = 0):
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args, **kwargs):
        return IteratorWrapperSeparate(
            context_partial(func, *args, **kwargs),
            max_size=max_size,
        )

    return wrap


class CoroutineWaiter:
    def __init__(
        self, loop: asyncio.AbstractEventLoop, coroutine_func,
        *args, **kwargs
    ):
        self.__func = partial(coroutine_func, *args, **kwargs)
        self.__loop = loop
        self.__event = threading.Event()
        self.__result = None
        self.__exception = None

    def _on_result(self, task: asyncio.Task):
        self.__exception = task.exception()
        if self.__exception is None:
            self.__result = task.result()
        self.__event.set()

    def _awaiter(self):
        task = self.__loop.create_task(self.__func())
        task.add_done_callback(self._on_result)

    def start(self):
        self.__loop.call_soon_threadsafe(self._awaiter)

    def wait(self):
        self.__event.wait()
        if self.__exception is not None:
            raise self.__exception
        return self.__result


def sync_wait_coroutine(loop, coro_func, *args, **kwargs):
    waiter = CoroutineWaiter(loop, coro_func, *args, **kwargs)
    waiter.start()
    return waiter.wait()
