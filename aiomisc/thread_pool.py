import asyncio

from threading import Thread
from queue import Queue, Empty

from concurrent.futures._base import Executor
from functools import partial, wraps
from types import MappingProxyType


class ThreadPoolExecutor(Executor):
    __slots__ = '__loop', '__futures', '__running', '__pool', '__tasks'

    def __init__(self, max_workers=None,
                 loop: asyncio.AbstractEventLoop = None):

        self.__loop = loop or asyncio.get_event_loop()
        self.__futures = set()
        self.__running = True

        self.__pool = set()
        self.__tasks = Queue(0)

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
        while self.__running:
            try:
                func, future = self.__tasks.get(timeout=1, block=True)
            except Empty:
                continue

            if future.done():
                continue

            result, exception = None, None

            try:
                result = func()
            except Exception as e:
                exception = e

            self.__loop.call_soon_threadsafe(
                self._set_result,
                future,
                result,
                exception,
            )

    def submit(self, fn, *args, **kwargs):
        future = self.__loop.create_future()     # type: asyncio.Future
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        self.__tasks.put_nowait((partial(fn, *args, **kwargs), future))
        return future

    def shutdown(self, wait=True):
        self.__running = False

        for f in filter(lambda x: not x.done(), self.__futures):
            f.set_exception(RuntimeError("Pool closed"))

    def __del__(self):
        self.shutdown()


def run_in_executor(func, executor=None, args=(), kwargs=MappingProxyType({})):
    loop = asyncio.get_event_loop()

    return loop.run_in_executor(
        executor, partial(func, *args, **kwargs)
    )


def threaded(func):
    @wraps(func)
    async def wrap(*args, **kwargs):
        return await run_in_executor(func=func, args=args, kwargs=kwargs)

    return wrap
