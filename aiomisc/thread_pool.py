import asyncio
import inspect
import logging
import time
import warnings
from asyncio.events import get_event_loop
from concurrent.futures._base import Executor
from functools import partial, wraps
from multiprocessing import cpu_count
import threading
from queue import Queue
from types import MappingProxyType

from .iterator_wrapper import IteratorWrapper


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


class ThreadPoolExecutor(Executor):
    __slots__ = (
        '__futures', '__pool', '__tasks',
        '__write_lock', '__thread_events',
    )

    def __init__(self, max_workers=max((cpu_count(), 4)), loop=None):
        if loop:
            warnings.warn(DeprecationWarning("loop argument is obsolete"))

        self.__futures = set()

        self.__pool = set()
        self.__thread_events = set()
        self.__tasks = Queue()
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
            args=(event,)
        )

        thread.daemon = True
        thread.start()
        return thread

    @staticmethod
    def _set_result(future, result, exception):
        if future.done():
            return

        if exception:
            future.set_exception(exception)
            return

        future.set_result(result)

    def _execute(self, func, future, loop: asyncio.AbstractEventLoop):
        if future.done():
            return

        result, exception = None, None

        if loop.is_closed():
            raise asyncio.CancelledError

        try:
            result = func()
        except Exception as e:
            exception = e

        if loop.is_closed():
            raise asyncio.CancelledError

        loop.call_soon_threadsafe(
            self._set_result,
            future,
            result,
            exception,
        )

    def _in_thread(self, event: threading.Event):
        while True:
            func, future, loop = self.__tasks.get()

            if func is None:
                self.__tasks.task_done()
                break

            try:
                if loop.is_closed():
                    log.warning(
                        "Event loop is closed. Call %r skipped",
                        func
                    )

                self._execute(func, future, loop)
            except asyncio.CancelledError:
                break
            finally:
                self.__tasks.task_done()

        event.set()

    def submit(self, fn, *args, **kwargs):
        if fn is None or not callable(fn):
            raise ValueError('First argument must be callable')

        with self.__write_lock:
            loop = asyncio.get_event_loop()
            future = loop.create_future()     # type: asyncio.Future
            self.__futures.add(future)
            future.add_done_callback(self.__futures.remove)

            self.__tasks.put_nowait((
                partial(fn, *args, **kwargs), future, loop
            ))

            return future

    def shutdown(self, wait=True):
        for _ in self.__pool:
            self.__tasks.put_nowait((None, None, None))

        if wait:
            while not all(e.is_set() for e in self.__thread_events):
                time.sleep(0)

        for f in filter(lambda x: not x.done(), self.__futures):
            f.set_exception(ThreadPoolException("Pool closed"))

    def __del__(self):
        self.shutdown()


def run_in_executor(func, executor=None, args=(),
                    kwargs=MappingProxyType({})) -> asyncio.Future:

    loop = get_event_loop()
    # noinspection PyTypeChecker
    return loop.run_in_executor(
        executor, context_partial(func, *args, **kwargs)
    )


async def _awaiter(future):
    try:
        return await future
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


def threaded(func):
    if asyncio.iscoroutinefunction(func):
        raise TypeError('Can not wrap coroutine')

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    @wraps(func)
    def wrap(*args, **kwargs):
        future = run_in_executor(func=func, args=args, kwargs=kwargs)
        return _awaiter(future)

    return wrap


def run_in_new_thread(func, args=(), kwargs=MappingProxyType({}),
                      detouch=True, no_return=False) -> asyncio.Future:
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
                set_result, target()
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

    loop.call_soon_threadsafe(thread.start)
    return future


def threaded_separate(func, detouch=True):
    if isinstance(func, bool):
        return partial(threaded_separate, detouch=detouch)

    if asyncio.iscoroutinefunction(func):
        raise TypeError('Can not wrap coroutine')

    @wraps(func)
    def wrap(*args, **kwargs):
        future = run_in_new_thread(
            func, args=args, kwargs=kwargs, detouch=detouch
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
