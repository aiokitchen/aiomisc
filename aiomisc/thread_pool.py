import asyncio
import inspect
import math
import weakref
from asyncio import AbstractEventLoop
from asyncio.events import get_event_loop
from concurrent.futures._base import Executor
from enum import IntEnum
from functools import partial, wraps, total_ordering
from multiprocessing import cpu_count
from queue import PriorityQueue, Empty
from threading import Thread
from types import MappingProxyType
from typing import Callable, Union

from .iterator_wrapper import IteratorWrapper


class ThreadPoolException(RuntimeError):
    pass


class Priority(IntEnum):
    LOW = 1024
    MEDIUM = 512
    HIGH = 128
    DEFAULT = MEDIUM


@total_ordering
class ThreadedTask:
    __slots__ = '__priority', '__future', '__callable'

    def __init__(self, priority: int, callable: Callable,
                 future: asyncio.Future):

        self.__priority = priority
        self.__future = future
        self.__callable = callable

    @property
    def callable(self):
        return self.__callable

    @property
    def future(self):
        return self.__future

    @property
    def priority(self):
        return self.__priority

    def __gt__(self, other):
        return self.__priority > other.priority

    def __eq__(self, other):
        return (
            self.priority == other.priority and
            self.callable == other.callable and
            self.future == other.future
        )


class ThreadPoolExecutor(Executor):
    __slots__ = '__loop', '__futures', '__running', '__pool', '__tasks'

    def __init__(self, max_workers=cpu_count(),
                 loop: AbstractEventLoop = None):

        self.__loop = loop or get_event_loop()
        self.__futures = set()
        self.__running = True

        self.__pool = set()
        self.__tasks = PriorityQueue(0)

        for idx in range(max_workers):
            thread = Thread(
                target=self._in_thread,
                name="[%d] Thread Pool" % idx,
                daemon=True,
            )

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

    def _in_thread(self):
        while self.__running and not self.__loop.is_closed():
            try:
                task = self.__tasks.get(
                    timeout=1, block=True
                )  # type: ThreadedTask
            except Empty:
                continue

            if task.future.done():
                continue

            result, exception = None, None

            if self.__loop.is_closed():
                break

            try:
                result = task.callable()
            except Exception as e:
                exception = e

            if self.__loop.is_closed():
                break

            self.__loop.call_soon_threadsafe(
                self._set_result,
                task.future,
                result,
                exception,
            )

    def submit(self, fn, *args, **kwargs):
        return self.submit_priority(
            fn, Priority.DEFAULT, args, kwargs
        )

    def submit_priority(self, fn, priority, args, kwargs):
        future = self.__loop.create_future()  # type: asyncio.Future
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        self.__tasks.put_nowait(
            ThreadedTask(
                priority=int(math.log(priority * 10) * self.__loop.time()),
                callable=partial(fn, *args, **kwargs),
                future=future,
            )
        )
        return future

    def shutdown(self, wait=True):
        self.__running = False

        for f in filter(lambda x: not x.done(), self.__futures):
            f.set_exception(ThreadPoolException("Pool closed"))

    def __del__(self):
        self.shutdown()


_loop_pool_mapping = weakref.WeakValueDictionary()


def _inspect_executor(loop):
    global _loop_pool_mapping

    loop_executor = _loop_pool_mapping.get(id(loop))

    if isinstance(loop_executor, ThreadPoolExecutor):
        return loop_executor

    executor = getattr(loop, '_default_executor', None)

    if executor is not None:
        return executor

    executor = ThreadPoolExecutor()

    loop.set_default_executor(executor)
    _loop_pool_mapping[id(loop)] = executor
    weakref.ref(executor, lambda: _loop_pool_mapping.pop(id(loop)))

    return executor


def run_in_executor(func, executor=None, args=(), kwargs=MappingProxyType({}),
                    priority: Union[int, Priority] = Priority.DEFAULT):
    loop = get_event_loop()

    if executor is None:
        executor = _inspect_executor(loop)

    if not isinstance(executor, ThreadPoolExecutor):
        return loop.run_in_executor(executor, partial(func, *args, **kwargs))

    return executor.submit_priority(func, priority, args, kwargs)


def threaded(func, priority=Priority.DEFAULT):
    if isinstance(func, (int, Priority)):
        return partial(threaded, priority=priority)

    @wraps(func)
    async def wrap(*args, **kwargs):
        return await run_in_executor(
            func=func,
            args=args,
            kwargs=kwargs,
            priority=priority
        )

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    return wrap


def threaded_iterable(func=None, max_size: int = 0):
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args, **kwargs):
        return IteratorWrapper(
            partial(func, *args, **kwargs),
            max_size=max_size,
        )

    return wrap
