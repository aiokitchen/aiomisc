import asyncio
import logging
from abc import ABC, abstractmethod
from typing import AsyncContextManager

from .utils import cancel_tasks


log = logging.getLogger(__name__)


class ContextManager(AsyncContextManager):
    __slots__ = "__aenter", "__aexit", "__instance"

    sentinel = object()

    def __init__(self, aenter, aexit):
        self.__aenter = aenter
        self.__aexit = aexit
        self.__instance = self.sentinel

    async def __aenter__(self):
        if self.__instance is not self.sentinel:
            raise RuntimeError("Reuse of context manager is not acceptable")

        self.__instance = await self.__aenter()
        return self.__instance

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.__aexit(self.__instance)


class PoolBase(ABC):
    __slots__ = (
        "_create_lock",
        "_instances",
        "_loop",
        "_recycle",
        "_recycle_bin",
        "_tasks",
        "_used",
    )

    def __init__(self, maxsize=None, recycle=None):
        assert (
            recycle is None or recycle > 0
        ), "recycle should be positive number or None"

        self._loop = asyncio.get_event_loop()

        self._recycle_bin = asyncio.Queue()
        self._instances = asyncio.Queue(maxsize=maxsize)
        self._used = set()
        self._recycle = recycle
        self._tasks = set()
        self._create_lock = asyncio.Lock()

        self.__create_task(self.__recycler())

    def __create_task(self, coro):
        task = self._loop.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.remove)
        return task

    async def __recycler(self):
        while True:
            instance = await self._recycle_bin.get()
            self.__create_task(self._destroy_instance(instance))
            self._recycle_bin.task_done()

    @abstractmethod
    async def _create_instance(self):
        pass

    @abstractmethod
    async def _destroy_instance(self, instance):
        pass

    # noinspection PyMethodMayBeStatic,PyUnusedLocal
    @abstractmethod
    async def _check_instance(self, instance):
        return True

    def __len__(self):
        return len(self._used) + self._instances.qsize()

    async def __acquire(self):
        if len(self) < self._instances.maxsize:
            async with self._create_lock:
                # check twice but no need to
                # lock for every time
                if len(self) < self._instances.maxsize:
                    instance = await self._create_instance()

                    if self._recycle:
                        self._loop.call_later(
                            self._recycle,
                            self._recycle_bin.put_nowait,
                            instance,
                        )

                    await self._instances.put(instance)

        instance = await self._instances.get()

        if not await self._check_instance(instance):
            # Bad instance must create a new one
            self._recycle_bin.put_nowait(instance)
            return await self.__acquire()

        self._used.add(instance)
        return instance

    async def __release(self, instance):
        self._used.remove(instance)
        self._instances.put_nowait(instance)

    def acquire(self):
        return ContextManager(self.__acquire, self.__release)

    async def close(self, timeout=None):
        instances = list(self._used)
        self._used.clear()

        while self._instances.qsize():
            try:
                instances.append(self._instances.get_nowait())
            except asyncio.QueueEmpty:
                break

        async def log_exception(coro):
            try:
                await coro()
            except Exception:
                log.exception("Exception when task execution")

        await asyncio.wait_for(
            asyncio.gather(
                *[
                    self.__create_task(
                        log_exception(self._destroy_instance(instance))
                    )
                    for instance in instances
                ]
            ),
            timeout=timeout,
        )

        await cancel_tasks(self._tasks)
