import asyncio
import contextvars
import inspect
import logging
import threading
import time
import warnings
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from dataclasses import dataclass, field
from functools import partial, wraps
from multiprocessing import cpu_count
from queue import SimpleQueue
from types import MappingProxyType
from typing import (
    Any, Awaitable, Callable, Coroutine, Dict, FrozenSet, Optional, Set, Tuple,
    TypeVar,
)

from ._context_vars import EVENT_LOOP
from .compat import ParamSpec
from .counters import Statistic
from .iterator_wrapper import IteratorWrapper


P = ParamSpec("P")
T = TypeVar("T")
F = TypeVar("F", bound=Callable[..., Any])
log = logging.getLogger(__name__)


def context_partial(
    func: F, *args: Any,
    **kwargs: Any,
) -> Any:
    warnings.warn(
        "context_partial has been deprecated and will be removed",
        DeprecationWarning,
    )
    context = contextvars.copy_context()
    return partial(context.run, func, *args, **kwargs)


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
    args: Tuple[Any, ...] = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    context: contextvars.Context = field(
        default_factory=contextvars.copy_context,
    )


def _set_workitem_result(
    future: asyncio.Future, result: Optional[Any],
    exception: Optional[BaseException],
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
            result = self.context.run(
                self.func, *self.args, **self.kwargs,
            )
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
            _set_workitem_result,
            self.future,
            result,
            exception,
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

        item: Optional[WorkItem] = super().get(*args, **kwargs)
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
        "__futures", "__pool", "__tasks",
        "__write_lock", "__thread_events",
    )

    DEFAULT_POOL_SIZE = min((max((cpu_count() or 1, 4)), 32))
    SHUTDOWN_TIMEOUT = 10

    def __init__(
        self, max_workers: int = DEFAULT_POOL_SIZE,
        statistic_name: Optional[str] = None,
    ) -> None:
        self.__futures: Set[asyncio.Future[Any]] = set()
        self.__thread_events: Set[threading.Event] = set()
        self.__tasks = TaskChannel()
        self.__write_lock = threading.RLock()
        self.__max_workers = max_workers
        self.__shutdown_event = threading.Event()
        self._statistic = ThreadPoolStatistic(statistic_name)

        threads = set()
        # starting minimum threads as possible
        for idx in range(2 if max_workers > 1 else 1):
            threads.add(self._start_thread(idx))

        self.__pool: FrozenSet[threading.Thread] = frozenset(threads)

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
            args=(
                self.__tasks,
                self._statistic,
                event,
                self.__shutdown_event,
            ),
        )

        thread.start()
        return thread

    def submit(  # type: ignore
        self, fn: F, *args: Any, **kwargs: Any,
    ) -> asyncio.Future:
        """Submit blocking function to the pool"""
        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        with self.__write_lock:
            if self.__shutdown_event.is_set():
                raise RuntimeError("Pool is shutdown")

            if (
                len(self.__pool) < self.__max_workers and
                len(self.__futures) >= len(self.__pool)
            ):
                self._adjust_thread_count()

            loop = asyncio.get_event_loop()
            future: asyncio.Future = loop.create_future()
            self.__futures.add(future)
            future.add_done_callback(self.__futures.discard)

            self.__tasks.put_nowait(
                WorkItem(
                    func=fn, args=args, kwargs=kwargs, loop=loop,
                    future=future, statistic=self._statistic,
                ),
            )

            self._statistic.submitted += 1
            return future

    # noinspection PyMethodOverriding
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
        new_threads_count = (
            min(pool_size * 2, self.__max_workers) - pool_size
        )
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
    executor: Optional[ThreadPoolExecutorBase] = None,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
) -> Awaitable[T]:
    try:
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(
            executor, partial(func, *args, **kwargs),
        )
    except RuntimeError:
        # In case the event loop is not running right now is
        # returning coroutine to avoid DeprecationWarning in Python 3.10
        async def lazy_wrapper() -> T:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor, partial(func, *args, **kwargs),
            )
        return lazy_wrapper()


async def _awaiter(future: asyncio.Future) -> T:
    try:
        result = await future
        return result
    except asyncio.CancelledError as e:
        if not future.done():
            future.set_exception(e)
        raise


def threaded(
    func: Callable[P, T],
) -> Callable[P, Awaitable[T]]:
    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    if inspect.isgeneratorfunction(func):
        return threaded_iterable(func)

    @wraps(func)
    def wrap(
        *args: P.args, **kwargs: P.kwargs,
    ) -> Awaitable[T]:
        return run_in_executor(func=func, args=args, kwargs=kwargs)

    return wrap


def run_in_new_thread(
    func: F,
    args: Any = (),
    kwargs: Any = MappingProxyType({}),
    detach: bool = True,
    no_return: bool = False,
    statistic_name: Optional[str] = None,
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


def threaded_separate(
    func: F,
    detach: bool = True,
) -> Callable[..., Awaitable[Any]]:
    if isinstance(func, bool):
        return partial(threaded_separate, detach=detach)

    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        future = run_in_new_thread(
            func, args=args, kwargs=kwargs, detach=detach,
        )
        return future

    return wrap


def threaded_iterable(
    func: Optional[F] = None,
    max_size: int = 0,
) -> Any:
    if isinstance(func, int):
        return partial(threaded_iterable, max_size=func)
    if func is None:
        return partial(threaded_iterable, max_size=max_size)

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        return IteratorWrapper(
            partial(func, *args, **kwargs),
            max_size=max_size,
        )

    return wrap


class IteratorWrapperSeparate(IteratorWrapper):
    def _run(self) -> Any:
        return run_in_new_thread(self._in_thread)


def threaded_iterable_separate(
    func: Optional[F] = None,
    max_size: int = 0,
) -> Any:
    if isinstance(func, int):
        return partial(threaded_iterable_separate, max_size=func)
    if func is None:
        return partial(threaded_iterable_separate, max_size=max_size)

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Any:
        return IteratorWrapperSeparate(
            partial(func, *args, **kwargs),
            max_size=max_size,
        )

    return wrap


class CoroutineWaiter:
    def __init__(
        self, coroutine: Coroutine[Any, Any, T],
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.__coro: Coroutine[Any, Any, T] = coroutine
        self.__loop = loop or EVENT_LOOP.get()
        self.__event = threading.Event()
        self.__result: Optional[T] = None
        self.__exception: Optional[BaseException] = None

    def _on_result(self, task: asyncio.Future) -> None:
        self.__exception = task.exception()
        if self.__exception is None:
            self.__result = task.result()
        self.__event.set()

    def _awaiter(self) -> None:
        task: asyncio.Future = self.__loop.create_task(self.__coro)
        task.add_done_callback(self._on_result)

    def start(self) -> None:
        self.__loop.call_soon_threadsafe(self._awaiter)

    def wait(self) -> Any:
        self.__event.wait()
        if self.__exception is not None:
            raise self.__exception
        return self.__result


def wait_coroutine(
    coro: Coroutine[Any, Any, T],
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> T:
    waiter = CoroutineWaiter(coro, loop)
    waiter.start()
    return waiter.wait()


def sync_wait_coroutine(
    loop: Optional[asyncio.AbstractEventLoop],
    coro_func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    return wait_coroutine(coro_func(*args, **kwargs), loop=loop)


def sync_await(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    async def awaiter() -> T:
        return await func(*args, **kwargs)
    return wait_coroutine(awaiter())
