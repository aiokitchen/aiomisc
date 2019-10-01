import asyncio
import inspect
from asyncio import AbstractEventLoop
from asyncio.events import get_event_loop
from concurrent.futures._base import Executor
from functools import partial, wraps
from multiprocessing import cpu_count
import threading
from queue import Queue
from types import MappingProxyType

from .iterator_wrapper import IteratorWrapper


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
        '__loop', '__futures', '__running', '__pool', '__tasks',
        '__write_lock',
    )

    def __init__(self, max_workers=max((cpu_count(), 2)),
                 loop: AbstractEventLoop = None):

        self.__loop = loop or get_event_loop()
        self.__futures = set()
        self.__running = True

        self.__pool = set()
        self.__tasks = Queue()
        self.__write_lock = threading.RLock()

        for idx in range(max_workers):
            thread = threading.Thread(
                target=self._in_thread,
                name="[%d] Thread Pool" % idx,
            )

            thread.daemon = True

            self.__pool.add(thread)
            # Starting the thread only after thread-pool will be started
            self.__loop.call_soon(thread.start)

        self.__pool = frozenset(self.__pool)

    @staticmethod
    def _set_result(future, result, exception):
        if future.done():
            return

        if exception:
            future.set_exception(exception)
            return

        future.set_result(result)

    def _execute(self, func, future):
        if future.done():
            return

        result, exception = None, None

        if self.__loop.is_closed():
            raise asyncio.CancelledError

        try:
            result = func()
        except Exception as e:
            exception = e

        if self.__loop.is_closed():
            raise asyncio.CancelledError

        self.__loop.call_soon_threadsafe(
            self._set_result,
            future,
            result,
            exception,
        )

    def _in_thread(self):
        while self.__running and not self.__loop.is_closed():
            try:
                func, future = self.__tasks.get()
                self._execute(func, future)
            except asyncio.CancelledError:
                break
            finally:
                self.__tasks.task_done()

    def submit(self, fn, *args, **kwargs):
        with self.__write_lock:
            future = self.__loop.create_future()     # type: asyncio.Future
            self.__futures.add(future)
            future.add_done_callback(self.__futures.remove)

            self.__tasks.put_nowait((partial(fn, *args, **kwargs), future))

            return future

    def shutdown(self, wait=True):
        self.__running = False

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
                      detouch=True) -> asyncio.Future:
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
