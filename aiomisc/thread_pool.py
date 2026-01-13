import asyncio
import contextvars
import inspect
import logging
import os
import threading
import time
import warnings
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Coroutine, Generator
from concurrent.futures import ThreadPoolExecutor as ThreadPoolExecutorBase
from dataclasses import dataclass, field
from functools import partial
from multiprocessing import cpu_count
from queue import SimpleQueue
from types import MappingProxyType
from typing import Any, Generic, TypeVar, Union, overload

from ._context_vars import EVENT_LOOP
from .compat import Concatenate, ParamSpec
from .counters import Statistic
from .iterator_wrapper import IteratorWrapper

# ParamSpec for functions
P = ParamSpec("P")
# bounded ParamSpec for bound methods
BP = ParamSpec("BP")

T = TypeVar("T")
S = TypeVar("S", bound=object)
F = TypeVar("F", bound=Callable[..., Any])
log = logging.getLogger(__name__)

THREADED_ITERABLE_DEFAULT_MAX_SIZE = int(
    os.getenv("THREADED_ITERABLE_DEFAULT_MAX_SIZE", 1024)
)


def context_partial(func: F, *args: Any, **kwargs: Any) -> Any:
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
        # starting minimum threads as possible
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
        # In case the event loop is not running right now is
        # returning coroutine to avoid DeprecationWarning in Python 3.10
        async def lazy_wrapper() -> T:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                executor, partial(func, *args, **kwargs)
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


class ThreadedBase(Generic[P, T], ABC):
    func: Callable[P, T]

    @abstractmethod
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def sync_call(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return self.func(*args, **kwargs)

    def async_call(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        return run_in_executor(func=self.func, args=args, kwargs=kwargs)

    def __repr__(self) -> str:
        f = getattr(self.func, "func", self.func)
        name = getattr(f, "__name__", f.__class__.__name__)
        return f"<{self.__class__.__name__} {name} at {id(self):#x}>"

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        return self.async_call(*args, **kwargs)


class Threaded(ThreadedBase[P, T]):
    func_type: type

    def __init__(self, func: Callable[P, T]) -> None:
        if isinstance(func, staticmethod):
            self.func_type = staticmethod
            self.func = func.__func__
        elif isinstance(func, classmethod):
            self.func_type = classmethod
            self.func = func.__func__
        else:
            self.func_type = type(func)
            self.func = func

        if asyncio.iscoroutinefunction(self.func):
            raise TypeError("Can not wrap coroutine")
        if inspect.isgeneratorfunction(self.func):
            raise TypeError("Can not wrap generator function")

    @overload
    def __get__(
        self: "Threaded[Concatenate[S, BP], T]",
        instance: S,
        owner: type | None = ...,
    ) -> "BoundThreaded[BP, T]": ...

    @overload
    def __get__(
        self: "Threaded[P, T]", instance: None, owner: type | None = ...
    ) -> "Threaded[P, T]": ...

    def __get__(
        self, instance: Any, owner: type | None = None
    ) -> "Threaded[P, T] | BoundThreaded[Any, T]":
        if self.func_type is staticmethod:
            return self
        elif self.func_type is classmethod:
            cls = owner if instance is None else type(instance)
            return BoundThreaded(self.func, cls)
        elif instance is not None:
            return BoundThreaded(self.func, instance)
        return self


class BoundThreaded(ThreadedBase[P, T]):
    __instance: Any

    def __init__(self, func: Callable[..., T], instance: Any) -> None:
        self.__instance = instance
        self.func = lambda *args, **kwargs: func(instance, *args, **kwargs)


@overload
def threaded(func: Callable[P, T]) -> Threaded[P, T]: ...


@overload
def threaded(
    func: Callable[P, Generator[T, None, None]],
) -> Callable[P, IteratorWrapper[P, T]]: ...


def threaded(
    func: Callable[P, T] | Callable[P, Generator[T, None, None]],
) -> Threaded[P, T] | Callable[P, IteratorWrapper[P, T]]:
    if inspect.isgeneratorfunction(func):
        return threaded_iterable(
            func, max_size=THREADED_ITERABLE_DEFAULT_MAX_SIZE
        )

    return Threaded(func)  # type: ignore


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


class ThreadedSeparate(Threaded[P, T]):
    __slots__ = Threaded.__slots__ + ("detach",)

    def __init__(self, func: Callable[P, T], detach: bool = True) -> None:
        super().__init__(func)
        self.detach = detach

    def async_call(self, *args: P.args, **kwargs: P.kwargs) -> Awaitable[T]:
        return run_in_new_thread(
            self.func, args=args, kwargs=kwargs, detach=self.detach
        )


def threaded_separate(
    func: Callable[P, T], detach: bool = True
) -> ThreadedSeparate[P, T]:
    if isinstance(func, bool):
        # noinspection PyTypeChecker
        return partial(threaded_separate, detach=detach)

    if asyncio.iscoroutinefunction(func):
        raise TypeError("Can not wrap coroutine")

    return ThreadedSeparate(func, detach=detach)


class ThreadedIterableBase(Generic[P, T], ABC):
    func: Callable[P, Generator[T, None, None]]
    max_size: int

    @abstractmethod
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def sync_call(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> Generator[T, None, None]:
        return self.func(*args, **kwargs)

    def async_call(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> IteratorWrapper[P, T]:
        return self.create_wrapper(*args, **kwargs)

    def create_wrapper(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> IteratorWrapper[P, T]:
        return IteratorWrapper(
            partial(self.func, *args, **kwargs), max_size=self.max_size
        )

    def __call__(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> IteratorWrapper[P, T]:
        return self.async_call(*args, **kwargs)


class ThreadedIterable(ThreadedIterableBase[P, T]):
    func_type: type

    def __init__(
        self, func: Callable[P, Generator[T, None, None]], max_size: int = 0
    ) -> None:
        if isinstance(func, staticmethod):
            self.func_type = staticmethod
            actual_func = func.__func__
        elif isinstance(func, classmethod):
            self.func_type = classmethod
            actual_func = func.__func__
        else:
            self.func_type = type(func)
            actual_func = func

        self.func = actual_func
        self.max_size = max_size

    @overload
    def __get__(
        self: "ThreadedIterable[Concatenate[S, BP], T]",
        instance: S,
        owner: type | None = ...,
    ) -> "BoundThreadedIterable[BP, T]": ...

    @overload
    def __get__(
        self: "ThreadedIterable[P, T]", instance: None, owner: type | None = ...
    ) -> "ThreadedIterable[P, T]": ...

    def __get__(
        self, instance: Any, owner: type | None = None
    ) -> "ThreadedIterable[P, T] | BoundThreadedIterable[Any, T]":
        if self.func_type is staticmethod:
            return self
        elif self.func_type is classmethod:
            cls = owner if instance is None else type(instance)
            return BoundThreadedIterable(self.func, cls, self.max_size)
        elif instance is not None:
            return BoundThreadedIterable(self.func, instance, self.max_size)
        return self


class BoundThreadedIterable(ThreadedIterableBase[P, T]):
    __instance: Any

    def __init__(
        self,
        func: Callable[..., Generator[T, None, None]],
        instance: Any,
        max_size: int = 0,
    ) -> None:
        self.__instance = instance
        self.func = lambda *args, **kwargs: func(instance, *args, **kwargs)
        self.max_size = max_size


@overload
def threaded_iterable(
    func: Callable[P, Generator[T, None, None]], *, max_size: int = 0
) -> "ThreadedIterable[P, T]": ...


@overload
def threaded_iterable(
    *, max_size: int = 0
) -> Callable[
    [Callable[P, Generator[T, None, None]]], ThreadedIterable[P, T]
]: ...


def threaded_iterable(
    func: Callable[P, Generator[T, None, None]] | None = None,
    *,
    max_size: int = 0,
) -> (
    ThreadedIterable[P, T]
    | Callable[[Callable[P, Generator[T, None, None]]], ThreadedIterable[P, T]]
):
    if func is None:
        return lambda f: ThreadedIterable(f, max_size=max_size)

    return ThreadedIterable(func, max_size=max_size)


class IteratorWrapperSeparate(IteratorWrapper):
    def _run(self) -> Any:
        return run_in_new_thread(self._in_thread)


class ThreadedIterableSeparate(ThreadedIterable[P, T]):
    def create_wrapper(
        self, *args: P.args, **kwargs: P.kwargs
    ) -> IteratorWrapperSeparate:
        return IteratorWrapperSeparate(
            partial(self.func, *args, **kwargs), max_size=self.max_size
        )


@overload
def threaded_iterable_separate(
    func: Callable[P, Generator[T, None, None]], *, max_size: int = 0
) -> "ThreadedIterable[P, T]": ...


@overload
def threaded_iterable_separate(
    *, max_size: int = 0
) -> Callable[
    [Callable[P, Generator[T, None, None]]], ThreadedIterableSeparate[P, T]
]: ...


def threaded_iterable_separate(
    func: Callable[P, Generator[T, None, None]] | None = None,
    *,
    max_size: int = 0,
) -> (
    ThreadedIterable[P, T]
    | Callable[
        [Callable[P, Generator[T, None, None]]], ThreadedIterableSeparate[P, T]
    ]
):
    if func is None:
        return lambda f: ThreadedIterableSeparate(f, max_size=max_size)

    return ThreadedIterableSeparate(func, max_size=max_size)


class CoroutineWaiter:
    def __init__(
        self,
        coroutine: Coroutine[Any, Any, T],
        loop: asyncio.AbstractEventLoop | None = None,
    ):
        self.__coro: Coroutine[Any, Any, T] = coroutine
        self.__loop = loop or EVENT_LOOP.get()
        self.__event = threading.Event()
        self.__result: T | None = None
        self.__exception: BaseException | None = None

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
    coro: Coroutine[Any, Any, T], loop: asyncio.AbstractEventLoop | None = None
) -> T:
    waiter = CoroutineWaiter(coro, loop)
    waiter.start()
    return waiter.wait()


def sync_wait_coroutine(
    loop: asyncio.AbstractEventLoop | None,
    coro_func: Callable[..., Coroutine[Any, Any, T]],
    *args: Any,
    **kwargs: Any,
) -> T:
    return wait_coroutine(coro_func(*args, **kwargs), loop=loop)


def sync_await(
    func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
) -> T:
    async def awaiter() -> T:
        return await func(*args, **kwargs)

    return wait_coroutine(awaiter())
