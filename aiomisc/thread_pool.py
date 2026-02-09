import asyncio
import contextvars
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from dataclasses import dataclass, field
from functools import partial
from multiprocessing import cpu_count
from queue import SimpleQueue
from types import MappingProxyType
from typing import Any, TypeVar

from aiothreads import (
    ChannelClosed,
    FromThreadChannel,
    sync_await,
    sync_wait_coroutine,
    threaded,
    threaded_iterable,
    threaded_iterable_separate,
    threaded_separate,
    wait_coroutine,
)
from aiothreads.iterator_wrapper import IteratorWrapper

from .counters import Statistic

T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
log = logging.getLogger(__name__)


class ThreadPoolException(RuntimeError):
    pass


class ThreadPoolStatistic(Statistic):
    threads: int
    done: int
    error: int
    success: int
    submitted: int
    sum_time: float


@dataclass(frozen=True)
class WorkItemBase:
    func: Callable[..., Any]
    statistic: ThreadPoolStatistic
    future: asyncio.Future
    loop: asyncio.AbstractEventLoop
    args: tuple[Any, ...] = field(default_factory=tuple)
    kwargs: dict[str, Any] = field(default_factory=dict)
    context: contextvars.Context = field(
        default_factory=contextvars.copy_context
    )


def _set_workitem_result(
    future: asyncio.Future, result: Any | None, exception: BaseException | None
) -> Any:
    if future.done():
        return

    if exception:
        future.set_exception(exception)
    else:
        future.set_result(result)


class WorkItem(WorkItemBase):
    def __call__(self, no_return: bool = False) -> None:
        if self.future.done():
            return

        if self.loop.is_closed():
            log.warning("Event loop is closed. Ignoring %r", self.func)
            raise asyncio.CancelledError

        result, exception = None, None
        delta = -time.monotonic()
        try:
            result = self.context.run(self.func, *self.args, **self.kwargs)
            self.statistic.success += 1
        except BaseException as e:
            self.statistic.error += 1
            exception = e
        finally:
            delta += time.monotonic()
            self.statistic.sum_time += delta
            self.statistic.done += 1

        if no_return:
            return

        if self.loop.is_closed():
            log.warning(
                "Event loop is closed. Forget execution result for %r",
                self.func,
            )
            raise asyncio.CancelledError

        self.loop.call_soon_threadsafe(
            _set_workitem_result, self.future, result, exception
        )


class TaskChannelCloseException(RuntimeError):
    pass


class TaskChannel(SimpleQueue):
    closed_event: threading.Event

    def __init__(self) -> None:
        super().__init__()
        self.closed_event = threading.Event()

    def get(self, *args: Any, **kwargs: Any) -> WorkItem:
        if self.closed_event.is_set():
            raise TaskChannelCloseException()

        item: WorkItem | None = super().get(*args, **kwargs)
        if item is None:
            self.put(None)
            raise TaskChannelCloseException()
        return item

    def close(self) -> None:
        self.closed_event.set()
        self.put(None)


def thread_pool_thread_loop(
    tasks: TaskChannel,
    statistic: ThreadPoolStatistic,
    stop_event: threading.Event,
    pool_shutdown_event: threading.Event,
) -> None:
    statistic.threads += 1

    try:
        while not pool_shutdown_event.is_set():
            tasks.get()()
    except (TaskChannelCloseException, asyncio.CancelledError):
        return None
    finally:
        stop_event.set()
        statistic.threads -= 1


class ThreadPoolExecutor(ThreadPoolExecutorBase):
    __slots__ = (
        "__futures",
        "__pool",
        "__tasks",
        "__thread_events",
        "__write_lock",
    )

    DEFAULT_POOL_SIZE = min((max((cpu_count() or 1, 4)), 32))
    SHUTDOWN_TIMEOUT = 10

    def __init__(
        self,
        max_workers: int = DEFAULT_POOL_SIZE,
        statistic_name: str | None = None,
    ) -> None:
        self.__futures: set[asyncio.Future[Any]] = set()
        self.__thread_events: set[threading.Event] = set()
        self.__tasks = TaskChannel()
        self.__write_lock = threading.RLock()
        self.__max_workers = max_workers
        self.__shutdown_event = threading.Event()
        self._statistic = ThreadPoolStatistic(statistic_name)

        threads = set()
        for idx in range(2 if max_workers > 1 else 1):
            threads.add(self._start_thread(idx))

        self.__pool: frozenset[threading.Thread] = frozenset(threads)

    def _start_thread(self, idx: int) -> threading.Thread:
        if self.__shutdown_event.is_set():
            raise RuntimeError("Can not create a thread after shutdown")

        event = threading.Event()
        self.__thread_events.add(event)

        thread_name = f"Thread {idx}"

        if self._statistic.name:
            thread_name += f" from pool {self._statistic.name}"

        thread = threading.Thread(
            target=thread_pool_thread_loop,
            name=thread_name.strip(),
            daemon=True,
            args=(self.__tasks, self._statistic, event, self.__shutdown_event),
        )

        thread.start()
        return thread

    def submit(  # type: ignore
        self, fn: F, *args: Any, **kwargs: Any
    ) -> asyncio.Future:
        """Submit blocking function to the pool"""
        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        with self.__write_lock:
            if self.__shutdown_event.is_set():
                raise RuntimeError("Pool is shutdown")

            if len(self.__pool) < self.__max_workers and len(
                self.__futures
            ) >= len(self.__pool):
                self._adjust_thread_count()

            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            self.__futures.add(future)
            future.add_done_callback(self.__futures.discard)

            self.__tasks.put_nowait(
                WorkItem(
                    func=fn,
                    args=args,
                    kwargs=kwargs,
                    loop=loop,
                    future=future,
                    statistic=self._statistic,
                )
            )

            self._statistic.submitted += 1
            return future

    def shutdown(self, wait: bool = True) -> None:  # type: ignore
        with self.__write_lock:
            if self.__shutdown_event.is_set():
                return None

            self.__shutdown_event.set()

            del self.__pool

            futures = self.__futures
            del self.__futures

            thread_events = self.__thread_events
            del self.__thread_events

            self.__tasks.close()

            while futures:
                future = futures.pop()
                if future.done():
                    continue
                future.set_exception(ThreadPoolException("Pool closed"))

            if not wait:
                return None

            start_time = time.monotonic()
            while not all(e.is_set() for e in thread_events):
                time.sleep(0.01)
                if (time.monotonic() - start_time) > self.SHUTDOWN_TIMEOUT:
                    log.warning(
                        "Waiting for shutting down the pool %r "
                        "cancelled due to timeout",
                        self,
                    )
                    return None

    def _adjust_thread_count(self) -> None:
        pool_size = len(self.__pool)
        new_threads_count = min(pool_size * 2, self.__max_workers) - pool_size
        if new_threads_count <= 0:
            return None

        threads = []
        for idx in range(pool_size, pool_size + new_threads_count):
            threads.append(self._start_thread(idx))
        self.__pool = frozenset(list(self.__pool) + threads)

    def __del__(self) -> None:
        self.__tasks.close()


def run_in_executor(
    func: Callable[..., T],
    executor: ThreadPoolExecutorBase | None = None,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
) -> Awaitable[T]:
    try:
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(executor, partial(func, *args, **kwargs))
    except RuntimeError:

        async def lazy_wrapper() -> T:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor, partial(func, *args, **kwargs)
            )

        return lazy_wrapper()


def run_in_new_thread(
    func: F,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
    detach: bool = True,
    no_return: bool = False,
    statistic_name: str | None = None,
) -> asyncio.Future:
    loop = asyncio.get_event_loop()
    future = loop.create_future()

    statistic = ThreadPoolStatistic(statistic_name)
    statistic.threads += 1

    thread = threading.Thread(
        target=WorkItem(
            func=func,
            args=args,
            kwargs=kwargs,
            loop=loop,
            future=future,
            statistic=statistic,
        ),
        name=func.__name__,
        kwargs=dict(no_return=no_return),
        daemon=detach,
    )
    statistic.submitted += 1
    loop.call_soon(thread.start)
    return future


class IteratorWrapperSeparate(IteratorWrapper):
    """IteratorWrapper that runs in a separate thread with statistics."""

    def _run(self) -> Any:
        return run_in_new_thread(self._in_thread)


__all__ = (
    "ChannelClosed",
    "FromThreadChannel",
    "IteratorWrapper",
    "IteratorWrapperSeparate",
    "TaskChannel",
    "TaskChannelCloseException",
    "ThreadPoolException",
    "ThreadPoolExecutor",
    "ThreadPoolStatistic",
    "WorkItem",
    "WorkItemBase",
    "run_in_executor",
    "run_in_new_thread",
    "sync_await",
    "sync_wait_coroutine",
    "threaded",
    "threaded_iterable",
    "threaded_iterable_separate",
    "threaded_separate",
    "wait_coroutine",
)
