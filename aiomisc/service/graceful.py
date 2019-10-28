import asyncio
from asyncio import Task
from typing import Coroutine

from aiomisc import Service


class GracefulMixin:

    __tasks = {}

    def create_graceful_task(self, coro: Coroutine, *, cancel: bool):
        task = asyncio.create_task(coro)
        task.add_done_callback(self.__pop_task)
        self.__tasks[task] = cancel
        return task

    def __pop_task(self, task: Task):
        self.__tasks.pop(task)

    async def graceful_shutdown(self):
        if self.__tasks:
            items = list(self.__tasks.items())
            to_cancel = [task for task, cancel in items if cancel]
            to_wait = [task for task, cancel in items if not cancel]
            await self.__wait_tasks(*to_cancel, cancel=True)
            await self.__wait_tasks(*to_wait, cancel=False)
            self.__tasks.clear()

    @staticmethod
    async def __wait_tasks(*tasks: Task, cancel: bool):
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

    async def start(self):
        raise NotImplementedError

    async def stop(self, exception: Exception = None):
        await self.graceful_shutdown()
