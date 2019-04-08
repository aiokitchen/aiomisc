import asyncio
import inspect
import time
import typing

import janus

T = typing.TypeVar('T')
R = typing.TypeVar('R')


class IteratorWrapper(typing.AsyncIterator):
    __slots__ = (
        "loop", "closed", "executor", "__close_event",
        "__queue", "__gen_task", "__gen_func"
    )

    def __init__(self, gen_func: typing.Generator[T, None, R],
                 loop=None, max_size=0, executor=None):

        self.loop = loop or asyncio.get_event_loop()
        self.closed = False
        self.executor = executor

        self.__close_event = asyncio.Event(loop=self.loop)
        self.__queue = janus.Queue(loop=self.loop, maxsize=max_size)
        self.__gen_task = None      # type: asyncio.Task
        self.__gen_func = gen_func  # type: typing.Callable

    @staticmethod
    def __throw(_):
        pass

    def __in_thread(self):
        queue = self.__queue.sync_q

        try:
            gen = iter(self.__gen_func())

            throw = self.__throw
            if inspect.isgenerator(gen):
                throw = gen.throw

            while not self.closed:
                item = next(gen)

                while queue.full():
                    time.sleep(0)

                    if self.closed:
                        throw(asyncio.CancelledError())
                        return

                queue.put((item, False))
        except StopIteration as e:
            if self.closed:
                return
            queue.put((e, None))
        except Exception as e:
            if self.closed:
                return
            queue.put((e, True))
        finally:
            self.loop.call_soon_threadsafe(self.__close_event.set)

    async def close(self):
        self.closed = True
        self.__queue.close()

        if not self.__gen_task.done():
            self.__gen_task.cancel()

        await asyncio.gather(
            self.__queue.wait_closed(),
            return_exceptions=True
        )

        await self.__close_event.wait()

    def __aiter__(self):
        if self.__gen_task is not None:
            return self

        self.__gen_task = self.loop.run_in_executor(
            self.executor, self.__in_thread
        )
        return self

    async def __anext__(self) -> typing.Awaitable[T]:
        item, is_exc = await self.__queue.async_q.get()
        self.__queue.async_q.task_done()

        if is_exc is None:
            await self.close()
            raise StopAsyncIteration(*item.args) from item
        elif is_exc:
            await self.close()
            raise item from item

        return item

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.closed:
            return

        await self.close()
