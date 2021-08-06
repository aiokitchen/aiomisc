import asyncio
import inspect
import threading
import typing as t
from collections import deque
from concurrent.futures import Executor

from aiomisc.counters import Statistic


T = t.TypeVar("T")
R = t.TypeVar("R")

GenType = t.Generator[T, R, None]
FuncType = t.Callable[[], GenType]


class IteratorWrapperStatistic(Statistic):
    started: int
    queue_size: int
    queue_length: int
    yielded: int
    enqueued: int


class IteratorWrapper(t.AsyncIterator):
    __slots__ = (
        "__close_event", "__closed", "__gen_func", "__gen_task", "__queue",
        "__queue_maxsize", "__read_event", "__write_event", "executor", "loop",
        "_statistic",
    )

    def __init__(
        self, gen_func: FuncType, loop: asyncio.AbstractEventLoop = None,
        max_size: int = 0, executor: Executor = None,
        statistic_name: t.Optional[str] = None,
    ):

        current_loop = loop or asyncio.get_event_loop()
        self.loop = current_loop    # type: asyncio.AbstractEventLoop
        self.executor = executor

        self.__closed = False
        self.__close_event = asyncio.Event()
        self.__queue = deque()      # type: t.Deque[t.Any]
        self.__queue_maxsize = max_size
        self.__gen_task = None      # type: t.Optional[asyncio.Task]
        self.__gen_func = gen_func  # type: t.Callable
        self.__write_event = threading.Event()
        self.__read_event = asyncio.Event()
        self._statistic = IteratorWrapperStatistic(statistic_name)
        self._statistic.queue_size = max_size

    @property
    def closed(self) -> bool:
        return self.__closed

    @staticmethod
    def __throw(_: t.Any) -> t.NoReturn:
        pass

    def _set_read_event(self) -> None:
        def setter() -> None:
            if self.__read_event.is_set():
                return
            self.__read_event.set()
        self.loop.call_soon_threadsafe(setter)

    def _in_thread(self) -> None:
        self._statistic.started += 1
        try:
            gen = iter(self.__gen_func())

            throw = self.__throw
            if inspect.isgenerator(gen):
                throw = gen.throw   # type: ignore

            while not self.closed:
                item = next(gen)

                while len(self.__queue) > self.__queue_maxsize:
                    self.__write_event.wait(0.1)

                    if self.closed:
                        throw(asyncio.CancelledError())
                        return

                self.__queue.append((item, False))
                self._statistic.enqueued += 1
                self._set_read_event()

                if self.__write_event.is_set():
                    self.__write_event.clear()
        except StopIteration as e:
            if self.closed:
                return
            self.__queue.append((e, None))
            self._set_read_event()
        except Exception as e:
            if self.closed:
                return
            self.__queue.append((e, True))
            self.loop.call_soon_threadsafe(self.__read_event.set)
        finally:
            self._statistic.started -= 1
            self._set_read_event()
            self.loop.call_soon_threadsafe(self.__close_event.set)

    async def _run(self) -> t.Any:
        return await self.loop.run_in_executor(self.executor, self._in_thread)

    async def close(self) -> None:
        self.__closed = True
        self.__queue.clear()

        if self.__gen_task is None:
            return

        if not self.__gen_task.done():
            self.__gen_task.cancel()

        await self.__close_event.wait()
        await asyncio.gather(
            self.__gen_task, loop=self.loop, return_exceptions=True,
        )
        del self.__queue

    def __aiter__(self) -> t.AsyncIterator[t.Any]:
        if self.__gen_task is not None:
            return self

        self.__gen_task = self.loop.create_task(self._run())
        return self

    async def __anext__(self) -> t.Awaitable[T]:
        while len(self.__queue) == 0:
            await self.__read_event.wait()

        item, is_exc = self.__queue.popleft()
        self.__write_event.set()

        if len(self.__queue) == 0:
            self.__read_event.clear()

        if is_exc is None:
            await self.close()
            raise StopAsyncIteration(*item.args) from item
        elif is_exc:
            await self.close()
            raise item from item

        self._statistic.yielded += 1
        return item

    async def __aenter__(self) -> "IteratorWrapper":
        return self

    async def __aexit__(
        self, exc_type: t.Any, exc_val: t.Any,
        exc_tb: t.Any,
    ) -> None:
        if self.closed:
            return

        await self.close()
