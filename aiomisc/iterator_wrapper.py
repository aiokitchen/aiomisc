import asyncio
import inspect
import threading
from abc import abstractmethod
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from concurrent.futures import Executor
from queue import Empty as QueueEmpty, Queue
from time import time
from types import TracebackType
from typing import Any, Generic, NoReturn, ParamSpec, TypeVar, Union
from weakref import finalize

from aiomisc.compat import EventLoopMixin
from aiomisc.counters import Statistic

T = TypeVar("T")
R = TypeVar("R")
P = ParamSpec("P")

GenType = Generator[T, None, None]
FuncType = Callable[[], GenType]


class ChannelClosed(RuntimeError):
    pass


class QueueWrapperBase:
    @abstractmethod
    def put(self, item: Any) -> None:
        raise NotImplementedError

    def get(self) -> Any:
        raise NotImplementedError


class DequeWrapper(QueueWrapperBase):
    __slots__ = ("queue",)

    def __init__(self) -> None:
        self.queue: deque[Any] = deque()

    def get(self) -> Any:
        if not self.queue:
            raise QueueEmpty
        return self.queue.popleft()

    def put(self, item: Any) -> None:
        return self.queue.append(item)


class QueueWrapper(QueueWrapperBase):
    __slots__ = ("queue",)

    def __init__(self, max_size: int) -> None:
        self.queue: Queue = Queue(maxsize=max_size)

    def put(self, item: Any) -> None:
        return self.queue.put(item)

    def get(self) -> Any:
        return self.queue.get_nowait()


def make_queue(max_size: int = 0) -> QueueWrapperBase:
    if max_size > 0:
        return QueueWrapper(max_size)
    return DequeWrapper()


class FromThreadChannel:
    SLEEP_LOW_THRESHOLD = 0.0001
    SLEEP_DIFFERENCE_DIVIDER = 10

    __slots__ = ("__closed", "__last_received_item", "queue")

    def __init__(self, maxsize: int = 0):
        self.queue: QueueWrapperBase = make_queue(max_size=maxsize)
        self.__closed = False
        self.__last_received_item: float = time()

    def close(self) -> None:
        self.__closed = True

    @property
    def is_closed(self) -> bool:
        return self.__closed

    def __enter__(self) -> "FromThreadChannel":
        return self

    def __exit__(
        self,
        exc_type: type[Exception],
        exc_val: Exception,
        exc_tb: TracebackType,
    ) -> None:
        self.close()

    def put(self, item: Any) -> None:
        if self.is_closed:
            raise ChannelClosed

        self.queue.put(item)
        self.__last_received_item = time()

    def _compute_sleep_time(self) -> float | int:
        if self.__last_received_item < 0:
            return 0

        delta = time() - self.__last_received_item

        if delta > 1:
            return 1

        sleep_time = delta / self.SLEEP_DIFFERENCE_DIVIDER

        if sleep_time < self.SLEEP_LOW_THRESHOLD:
            return 0
        return sleep_time

    def __await__(self) -> Any:
        while True:
            try:
                res = self.queue.get()
                return res
            except QueueEmpty:
                if self.is_closed:
                    raise ChannelClosed

                sleep_time = self._compute_sleep_time()
                yield from asyncio.sleep(sleep_time).__await__()

    async def get(self) -> Any:
        return await self


class IteratorWrapperStatistic(Statistic):
    started: int
    queue_size: int
    queue_length: int
    yielded: int
    enqueued: int


class IteratorWrapper(Generic[P, T], AsyncIterator, EventLoopMixin):
    __slots__ = (
        "__channel",
        "__close_event",
        "__gen_func",
        "__gen_task",
        "_run_lock",
        "_statistic",
        "executor",
    ) + EventLoopMixin.__slots__

    def __init__(
        self,
        gen_func: Callable[P, Generator[T, None, None]],
        loop: asyncio.AbstractEventLoop | None = None,
        max_size: int = 0,
        executor: Executor | None = None,
        statistic_name: str | None = None,
    ):
        self._loop = loop
        self.executor = executor

        self.__close_event = asyncio.Event()
        self.__channel: FromThreadChannel = FromThreadChannel(maxsize=max_size)
        self.__gen_task: asyncio.Future | None = None
        self.__gen_func: Callable = gen_func
        self._statistic = IteratorWrapperStatistic(statistic_name)
        self._statistic.queue_size = max_size
        self._run_lock = threading.Lock()

    @property
    def closed(self) -> bool:
        return self.__channel.is_closed

    @staticmethod
    def __throw(_: Any) -> NoReturn:
        raise

    def _in_thread(self) -> None:
        self._statistic.started += 1
        with self.__channel:
            try:
                gen = iter(self.__gen_func())

                throw = self.__throw
                if inspect.isgenerator(gen):
                    throw = gen.throw  # type: ignore

                while not self.closed:
                    item = next(gen)
                    try:
                        self.__channel.put((item, False))
                    except Exception as e:
                        throw(e)
                        self.__channel.close()
                        break
                    finally:
                        del item

                    self._statistic.enqueued += 1
            except StopIteration:
                return
            except Exception as e:
                if self.closed:
                    return
                self.__channel.put((e, True))
            finally:
                self._statistic.started -= 1
                self.loop.call_soon_threadsafe(self.__close_event.set)

    def close(self) -> Awaitable[None]:
        self.__channel.close()
        # if the iterator inside thread is blocked on `.put()`
        # we need to wake it up to signal that it is closed.
        try:
            self.__channel.queue.get()
        except QueueEmpty:
            pass
        return asyncio.ensure_future(self.wait_closed())

    async def wait_closed(self) -> None:
        await self.__close_event.wait()
        if self.__gen_task:
            await asyncio.gather(self.__gen_task, return_exceptions=True)

    def _run(self) -> Any:
        return self.loop.run_in_executor(self.executor, self._in_thread)

    def __start_generator(self) -> None:
        if not self.loop.is_running():
            raise RuntimeError("Event loop is not running")

        with self._run_lock:
            if self.__gen_task is not None:
                return
            gen_task = self._run()
            if gen_task is None:
                raise RuntimeError("Iterator task was not created")
            self.__gen_task = gen_task

    def __aiter__(self) -> AsyncIterator[T]:
        self.__start_generator()
        return IteratorProxy(self, self.close)

    async def __anext__(self) -> T:
        try:
            item, is_exc = await self.__channel.get()
        except ChannelClosed:
            await self.wait_closed()
            raise StopAsyncIteration

        if is_exc:
            await self.close()
            raise item from item

        self._statistic.yielded += 1
        return item

    async def __aenter__(self) -> "IteratorWrapper":
        self.__start_generator()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.closed:
            return

        await self.close()


class IteratorProxy(Generic[T], AsyncIterator):
    def __init__(
        self, iterator: AsyncIterator[T], finalizer: Callable[[], Any]
    ):
        self.__iterator = iterator
        finalize(self, finalizer)

    def __anext__(self) -> Awaitable[T]:
        return self.__iterator.__anext__()
