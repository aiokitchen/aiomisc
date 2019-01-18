import asyncio
import inspect
import time
from typing import AsyncIterator, Awaitable, Generator, TypeVar

import janus


T = TypeVar('T')
R = TypeVar('R')


class IteratorWrapper(AsyncIterator):
    def __init__(self, gen_func: Generator[T, None, R], loop=None, max_size=0):
        self.loop = loop or asyncio.get_event_loop()
        self.closed = False

        self.__close_event = asyncio.Event(loop=self.loop)
        self.__queue = janus.Queue(loop=self.loop, maxsize=max_size)
        self.__gen_task = self.loop.run_in_executor(
            None, self.__in_thread, gen_func
        )

    @staticmethod
    def __throw(_):
        pass

    def __in_thread(self, gen_func):
        queue = self.__queue.sync_q
        gen = iter(gen_func())

        throw = self.__throw
        if inspect.isgenerator(gen):
            throw = gen.throw

        try:
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
        await asyncio.gather(
            self.__queue.wait_closed(),
            return_exceptions=True
        )

        await self.__close_event.wait()

    async def __anext__(self) -> Awaitable[T]:
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
