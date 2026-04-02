import functools
import inspect
import logging
import weakref
from asyncio import CancelledError, Event, Future, Lock, wait_for
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from inspect import Parameter
from threading import RLock
from typing import Any, Generic, Protocol, TypeVar

from .compat import EventLoopMixin
from .counters import Statistic

log = logging.getLogger(__name__)


V = TypeVar("V")
R = TypeVar("R")


@dataclass(frozen=True)
class Arg(Generic[V, R]):
    value: V
    future: "Future[R]"


@dataclass(slots=True)
class Bucket(Generic[V, R]):
    items: list[Arg[V, R]] = field(default_factory=list)
    event: Event = field(default_factory=Event)
    lock: Lock = field(default_factory=Lock)
    first_call_at: float | None = None


class ResultNotSetError(Exception):
    pass


class AggregateAsyncFunc(Protocol, Generic[V, R]):
    __name__: str

    async def __call__(self, *args: Arg[V, R]) -> None: ...


class AggregateStatistic(Statistic):
    leeway_ms: float
    max_count: int
    success: int
    error: int
    done: int
    batch_size: int


def _has_variadic_positional(func: Callable[..., Any]) -> bool:
    return any(
        parameter.kind == Parameter.VAR_POSITIONAL
        for parameter in inspect.signature(func).parameters.values()
    )


class AggregatorAsync(EventLoopMixin, Generic[V, R]):
    _func: AggregateAsyncFunc[V, R]
    _max_count: int | None
    _leeway: float
    _buckets: dict[tuple, Bucket[V, R]]

    def __init__(
        self,
        func: AggregateAsyncFunc[V, R],
        *,
        leeway_ms: float,
        max_count: int | None = None,
        statistic_name: str | None = None,
    ):
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments"
            )

        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")

        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")

        self._func = func
        self._max_count = max_count
        self._leeway = leeway_ms / 1000
        self._buckets = {}
        self._statistic = AggregateStatistic(statistic_name or func.__name__)
        self._statistic.leeway_ms = self.leeway_ms
        self._statistic.max_count = max_count or 0
        self._buckets_mutex = RLock()

    def _get_bucket(self, kwargs_key: tuple) -> Bucket[V, R]:
        with self._buckets_mutex:
            if kwargs_key not in self._buckets:
                self._buckets[kwargs_key] = Bucket()
            return self._buckets[kwargs_key]

    def _detach_bucket(self, kwargs_key: tuple) -> Bucket[V, R] | None:
        with self._buckets_mutex:
            return self._buckets.pop(kwargs_key, None)

    @property
    def max_count(self) -> int | None:
        return self._max_count

    @property
    def leeway_ms(self) -> float:
        return self._leeway * 1000

    @property
    def count(self) -> int:
        return sum(len(b.items) for b in self._buckets.values())

    async def _execute(
        self, *, items: list[Arg[V, R]], kwargs: dict[str, Any] | None = None
    ) -> None:
        self._statistic.batch_size += len(items)
        try:
            await self._func(*items, **(kwargs or {}))
            self._statistic.success += 1
        except CancelledError:
            raise
        except Exception as e:
            for item in items:
                if not item.future.done():
                    item.future.set_exception(e)
            self._statistic.error += 1
            return
        finally:
            self._statistic.done += 1

        for item in items:
            if not item.future.done():
                item.future.set_exception(ResultNotSetError)

    async def aggregate(self, arg: V, **kwargs: Any) -> R:
        kwargs_key = tuple(sorted(kwargs.items()))
        bucket = self._get_bucket(kwargs_key)

        if bucket.first_call_at is None:
            bucket.first_call_at = self.loop.time()
        first_call_at = bucket.first_call_at

        items = bucket.items
        event = bucket.event
        lock = bucket.lock

        future: Future[R] = Future()
        items.append(Arg(value=arg, future=future))

        if len(items) == self.max_count:
            event.set()
            self._detach_bucket(kwargs_key)
        else:
            try:
                await wait_for(
                    event.wait(),
                    timeout=(first_call_at + self._leeway - self.loop.time()),
                )
            except TimeoutError:
                log.debug(
                    "Aggregation timeout of %s for batch started at %.4f "
                    "with %d calls after %.2f ms",
                    self._func.__name__,
                    first_call_at,
                    len(items),
                    (self.loop.time() - first_call_at) * 1000,
                )

        if kwargs_key in self._buckets and self._buckets[kwargs_key] is bucket:
            self._detach_bucket(kwargs_key)

        async with lock:
            if not future.done():
                await self._execute(
                    items=items, kwargs=kwargs if kwargs else None
                )

        return await future


S = TypeVar("S", contravariant=True)
T = TypeVar("T", covariant=True)


class AggregateFunc(Protocol[S, T]):
    __name__: str

    async def __call__(self, *args: S) -> Iterable[T]: ...


def _to_async_aggregate(func: AggregateFunc[V, R]) -> AggregateAsyncFunc[V, R]:
    @functools.wraps(
        func,
        assigned=tuple(
            item
            for item in functools.WRAPPER_ASSIGNMENTS
            if item != "__annotations__"
        ),
    )
    async def wrapper(*args: Arg[V, R], **kwargs: Any) -> None:
        args_ = [item.value for item in args]
        results = await func(*args_, **kwargs)
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
        max_count: int | None = None,
        statistic_name: str | None = None,
    ) -> None:
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments"
            )

        super().__init__(
            _to_async_aggregate(func),
            leeway_ms=leeway_ms,
            max_count=max_count,
            statistic_name=statistic_name,
        )


class AggregateDescriptor(Generic[V, R]):
    def __init__(
        self,
        func: Callable[..., Any],
        *,
        leeway_ms: float,
        max_count: int | None,
        aggregator_class: type[AggregatorAsync[V, R]],
        statistic_name: str | None = None,
    ):
        functools.update_wrapper(self, func)
        self.func = func
        self.leeway_ms = leeway_ms
        self.max_count = max_count
        self.aggregator_class = aggregator_class
        self.statistic_name = statistic_name
        self.plain_aggregator: AggregatorAsync[V, R] | None = None
        self.instance_cache: weakref.WeakKeyDictionary[
            Any, AggregatorAsync[V, R]
        ] = weakref.WeakKeyDictionary()

    def __call__(self, arg: V, **kwargs: Any) -> Coroutine[Any, Any, R]:
        if self.plain_aggregator is None:
            name = self.statistic_name or self.func.__name__
            self.plain_aggregator = self.aggregator_class(
                self.func,
                leeway_ms=self.leeway_ms,
                max_count=self.max_count,
                statistic_name=name,
            )
        return self.plain_aggregator.aggregate(arg, **kwargs)

    def __get__(
        self, obj: Any, objtype: type | None = None
    ) -> Callable[..., Coroutine[Any, Any, R]]:
        if obj is None:
            return self
        if obj not in self.instance_cache:
            bound = functools.partial(self.func, obj)
            functools.update_wrapper(bound, self.func)
            name = self.statistic_name or (
                f"{type(obj).__name__}.{self.func.__name__}"
            )
            self.instance_cache[obj] = self.aggregator_class(
                bound,  # type: ignore[arg-type]
                leeway_ms=self.leeway_ms,
                max_count=self.max_count,
                statistic_name=name,
            )
        return self.instance_cache[obj].aggregate


def aggregate(
    leeway_ms: float,
    max_count: int | None = None,
    statistic_name: str | None = None,
) -> Callable[[AggregateFunc[V, R]], AggregateDescriptor[V, R]]:
    """
    Parametric decorator that aggregates multiple
    (but no more than ``max_count`` defaulting to ``None``) single-argument
    executions (``res1 = await func(arg1)``, ``res2 = await func(arg2)``, ...)
    of an asynchronous function with variadic positional arguments
    (``async def func(*args, pho=1, bo=2) -> Iterable``) into its single
    execution with multiple positional arguments
    (``res1, res2, ... = await func(arg1, arg2, ...)``) collected within a time
    window ``leeway_ms``.

    Keyword arguments passed by callers are forwarded to the decorated
    function. Calls with different keyword arguments are batched
    separately.

    Supports the descriptor protocol: when applied to a method, each
    class instance gets its own independent aggregator.

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

    def decorator(func: AggregateFunc[V, R]) -> AggregateDescriptor[V, R]:
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments"
            )
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")
        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")
        return AggregateDescriptor(
            func,
            leeway_ms=leeway_ms,
            max_count=max_count,
            aggregator_class=Aggregator,
            statistic_name=statistic_name,
        )

    return decorator


def aggregate_async(
    leeway_ms: float,
    max_count: int | None = None,
    statistic_name: str | None = None,
) -> Callable[[AggregateAsyncFunc[V, R]], AggregateDescriptor[V, R]]:
    """
    Same as ``aggregate``, but with ``func`` arguments of type ``Arg``
    containing ``value`` and ``future`` attributes instead. In this setting
    ``func`` is responsible for setting individual results/exceptions for all
    of the futures or throwing an exception (it will propagate to futures
    automatically). If ``func`` mistakenly does not set a result of some
    future, then, ``ResultNotSetError`` exception is set.

    Keyword arguments passed by callers are forwarded to the decorated
    function. Calls with different keyword arguments are batched
    separately.

    Supports the descriptor protocol: when applied to a method, each
    class instance gets its own independent aggregator.

    :return:
    """

    def decorator(func: AggregateAsyncFunc[V, R]) -> AggregateDescriptor[V, R]:
        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments"
            )
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")
        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")
        return AggregateDescriptor(
            func,
            leeway_ms=leeway_ms,
            max_count=max_count,
            aggregator_class=AggregatorAsync,
            statistic_name=statistic_name,
        )

    return decorator
