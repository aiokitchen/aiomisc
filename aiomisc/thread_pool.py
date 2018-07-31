import asyncio

from threading import Thread
from queue import Queue, Empty

from concurrent.futures._base import Executor
from functools import partial, wraps


class ThreadPoolExecutor(Executor):
    __slots__ = '__loop', '__futures', '__running', '__pool', '__tasks'

    def __init__(self, processes=None, loop: asyncio.AbstractEventLoop = None):
        self.__loop = loop or asyncio.get_event_loop()
        self.__futures = set()
        self.__running = True

        self.__pool = set()
        self.__tasks = Queue(0)

        for idx in range(processes):
            thread = Thread(
                target=self._in_thread,
                name="[%d] Thread Pool" % idx,
                daemon=True,
            )

            self.__pool.add(thread)
            # Starting the thread only after thread-pool will be started
            self.__loop.call_soon(thread.start)

        self.__pool = frozenset(self.__pool)

    def _in_thread(self):
        while self.__running:
            try:
                func, future = self.__tasks.get(timeout=1, block=True)
            except Empty:
                continue

            try:
                self.__loop.call_soon_threadsafe(future.set_result, func())
            except Exception as e:
                self.__loop.call_soon_threadsafe(future.set_exception, e)

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


def threaded(func):
    @wraps(func)
    async def wrap(*args, **kwargs):
        loop = asyncio.get_event_loop()

        return await loop.run_in_executor(
            None, partial(func, *args, **kwargs)
        )

    return wrap
