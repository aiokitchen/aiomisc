import asyncio
from asyncio import Task, get_event_loop
from contextlib import suppress
from typing import Coroutine, Dict

from . import Service
from ..timeout import timeout


class GracefulMixin:

    __tasks: Dict[Task, bool] = {}

    def create_graceful_task(self, coro: Coroutine, *, cancel: bool) -> Task:
        task = get_event_loop().create_task(coro)
        task.add_done_callback(self.__pop_task)
        self.__tasks[task] = cancel
        return task

    def __pop_task(self, task: Task) -> None:
        self.__tasks.pop(task)

    async def graceful_shutdown(self, *, wait_timeout: float = None) -> None:
        if self.__tasks:
            items = list(self.__tasks.items())
            to_cancel = [task for task, cancel in items if cancel]
            to_wait = [task for task, cancel in items if not cancel]

            waiter = self.__wait_tasks(*to_cancel, cancel=True)
            await waiter

            if wait_timeout is None:
                waiter = self.__wait_tasks
            else:
                waiter = timeout(wait_timeout)(self.__wait_tasks)
            waiter = waiter(*to_wait, cancel=False)

            with suppress(asyncio.TimeoutError):
                await waiter

            self.__tasks.clear()

    @staticmethod
    async def __wait_tasks(*tasks: Task, cancel: bool) -> None:
        if not tasks:
            return

        to_stop = []

        for task in tasks:
            if task.done():
                continue

            if cancel:
                task.cancel()

            to_stop.append(task)

        await asyncio.gather(
            *to_stop,
            return_exceptions=True,
        )


class GracefulService(Service, GracefulMixin):

    graceful_wait_timeout = None  # type: float # in seconds

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, exception: Exception = None) -> None:
        await self.graceful_shutdown(wait_timeout=self.graceful_wait_timeout)
