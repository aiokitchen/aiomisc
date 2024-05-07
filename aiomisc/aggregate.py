import asyncio
import functools
import inspect
import logging
from asyncio import CancelledError, Event, Future, Lock, wait_for
from dataclasses import dataclass
from inspect import Parameter
from typing import (
    Any,
    Callable,
    Coroutine,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    TypeVar,
)

from .compat import EventLoopMixin
from .counters import Statistic


log = logging.getLogger(__name__)


V = TypeVar("V")
R = TypeVar("R")


@dataclass(frozen=True)
class Arg(Generic[V, R]):
    value: V
    future: "Future[R]"


class ResultNotSetError(Exception):
    pass


class AggregateAsyncFunc(Protocol, Generic[V, R]):
    __name__: str

    async def __call__(self, *args: Arg[V, R]) -> None:
        ...


class AggregateStatistic(Statistic):
    leeway_ms: float
    max_count: int
    success: int
    error: int
    done: int


def _has_variadic_positional(func: Callable[..., Any]) -> bool:
    return any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in inspect.signature(func).parameters.values()
    )


class AggregatorAsync(EventLoopMixin, Generic[V, R]):

    _func: AggregateAsyncFunc[V, R]
    _max_count: Optional[int]
    _leeway: float
    _first_call_at: Optional[float]
    _args: list
    _futures: "List[Future[R]]"
    _event: Event
    _lock: Lock

    def __init__(
        self, func: AggregateAsyncFunc[V, R], *, leeway_ms: float,
        max_count: Optional[int] = None,
        statistic_name: Optional[str] = None,
    ):
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments",
            )

        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")

        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")

        self._func = func
        self._max_count = max_count
        self._leeway = leeway_ms / 1000
        self._clear()
        self._statistic = AggregateStatistic(statistic_name)
        self._statistic.leeway_ms = self.leeway_ms
        self._statistic.max_count = max_count or 0

    def _clear(self) -> None:
        self._first_call_at = None
        self._args = []
        self._futures = []
        self._event = Event()
        self._lock = Lock()

    @property
    def max_count(self) -> Optional[int]:
        return self._max_count

    @property
    def leeway_ms(self) -> float:
        return self._leeway * 1000

    @property
    def count(self) -> int:
        return len(self._args)

    async def _execute(
        self,
        *,
        args: List[V],
        futures: "List[Future[R]]",
    ) -> None:
        args_ = [
            Arg(value=arg, future=future)
            for arg, future in zip(args, futures)
        ]
        try:
            await self._func(*args_)
            self._statistic.success += 1
        except CancelledError:
            # Other waiting tasks can try to finish the job instead.
            raise
        except Exception as e:
            self._set_exception(e, futures)
            self._statistic.error += 1
            return
        finally:
            self._statistic.done += 1

        # Validate that all results/exceptions are set by the func
        for future in futures:
            if not future.done():
                future.set_exception(ResultNotSetError)

    def _set_exception(
            self, exc: Exception, futures: List["Future[R]"],
    ) -> None:
        for future in futures:
            if not future.done():
                future.set_exception(exc)

    async def aggregate(self, arg: V) -> R:
        if self._first_call_at is None:
            self._first_call_at = self.loop.time()
        first_call_at = self._first_call_at

        args: list = self._args
        futures: "List[Future[R]]" = self._futures
        event: Event = self._event
        lock: Lock = self._lock
        args.append(arg)
        future: "Future[R]" = Future()
        futures.append(future)

        if self.count == self.max_count:
            event.set()
            self._clear()
        else:
            # Waiting for max_count requests or a timeout
            try:
                await wait_for(
                    event.wait(),
                    timeout=first_call_at + self._leeway - self.loop.time(),
                )
            except asyncio.TimeoutError:
                log.debug(
                    "Aggregation timeout of %s for batch started at %.4f "
                    "with %d calls after %.2f ms",
                    self._func.__name__, first_call_at, len(futures),
                    (self.loop.time() - first_call_at) * 1000,
                )

        # Clear only if not cleared already
        if args is self._args:
            self._clear()

        # Trying to acquire the lock to execute the aggregated function
        async with lock:
            if not future.done():
                await self._execute(args=args, futures=futures)
        await future
        return future.result()


S = TypeVar("S", contravariant=True)
T = TypeVar("T", covariant=True)


class AggregateFunc(Protocol, Generic[S, T]):
    __name__: str

    async def __call__(self, *args: S) -> Iterable[T]:
        ...


def _to_async_aggregate(func: AggregateFunc[V, R]) -> AggregateAsyncFunc[V, R]:
    @functools.wraps(
        func,
        assigned=tuple(
            item
            for item in functools.WRAPPER_ASSIGNMENTS
            if item != "__annotations__"
        ),
    )
    async def wrapper(*args: Arg[V, R]) -> None:
        args_ = [item.value for item in args]
        results = await func(*args_)
        for res, arg in zip(results, args):
            if not arg.future.done():
                arg.future.set_result(res)

    return wrapper


class Aggregator(AggregatorAsync[V, R], Generic[V, R]):
    def __init__(
        self,
        func: AggregateFunc[V, R],
        *,
        leeway_ms: float,
        max_count: Optional[int] = None,
        statistic_name: Optional[str] = None,
    ) -> None:
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments",
            )

        super().__init__(
            _to_async_aggregate(func),
            leeway_ms=leeway_ms,
            max_count=max_count,
            statistic_name=statistic_name,
        )


def aggregate(
    leeway_ms: float, max_count: Optional[int] = None
) -> Callable[[AggregateFunc[V, R]], Callable[[V], Coroutine[Any, Any, R]]]:
    """
    Parametric decorator that aggregates multiple
    (but no more than ``max_count`` defaulting to ``None``) single-argument
    executions (``res1 = await func(arg1)``, ``res2 = await func(arg2)``, ...)
    of an asynchronous function with variadic positional arguments
    (``async def func(*args, pho=1, bo=2) -> Iterable``) into its single
    execution with multiple positional arguments
    (``res1, res2, ... = await func(arg1, arg2, ...)``) collected within a time
    window ``leeway_ms``.

    .. note::

        ``func`` must return a sequence of values of length equal to the
        number of arguments (and in the same order).

    .. note::

        if some unexpected error occurs, exception is propagated to each
        future; to set an individual error for each aggregated call refer
        to ``aggregate_async``.

    :param leeway_ms: The maximum approximate delay between the first
           collected argument and the aggregated execution.
    :param max_count: The maximum number of arguments to call decorated
           function with. Default ``None``.

    :return:
    """
    def decorator(
        func: AggregateFunc[V, R]
    ) -> Callable[[V], Coroutine[Any, Any, R]]:
        aggregator = Aggregator(
            func, max_count=max_count, leeway_ms=leeway_ms,
        )
        return aggregator.aggregate
    return decorator


def aggregate_async(
    leeway_ms: float, max_count: Optional[int] = None,
) -> Callable[
    [AggregateAsyncFunc[V, R]],
    Callable[[V], Coroutine[Any, Any, R]]
]:
    """
    Same as ``aggregate``, but with ``func`` arguments of type ``Arg``
    containing ``value`` and ``future`` attributes instead. In this setting
    ``func`` is responsible for setting individual results/exceptions for all
    of the futures or throwing an exception (it will propagate to futures
    automatically). If ``func`` mistakenly does not set a result of some
    future, then, ``ResultNotSetError`` exception is set.

    :return:
    """
    def decorator(
        func: AggregateAsyncFunc[V, R]
    ) -> Callable[[V], Coroutine[Any, Any, R]]:
        aggregator = AggregatorAsync(
            func, max_count=max_count, leeway_ms=leeway_ms,
        )
        return aggregator.aggregate
    return decorator
