import asyncio
import functools
import inspect
import logging
from asyncio import CancelledError, Event, Future, Lock, wait_for
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from inspect import Parameter
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

    async def __call__(self, *args: Arg[V, R], **kwargs: Any) -> None: ...


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
    _max_count: int | None
    _leeway: float
    _buckets: dict[frozenset[tuple[str, Any]], Bucket[V, R]]

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
        self._statistic = AggregateStatistic(statistic_name)
        self._statistic.leeway_ms = self.leeway_ms
        self._statistic.max_count = max_count or 0

    @property
    def max_count(self) -> int | None:
        return self._max_count

    @property
    def leeway_ms(self) -> float:
        return self._leeway * 1000

    @property
    def count(self) -> int:
        return sum(len(bucket.items) for bucket in self._buckets.values())

    async def _execute(
        self, *, items: list[Arg[V, R]], kwargs: dict[str, Any]
    ) -> None:
        try:
            await self._func(*items, **kwargs)
            self._statistic.success += 1
        except CancelledError:
            # Other waiting tasks can try to finish the job instead.
            raise
        except Exception as e:
            self._set_exception(e, items)
            self._statistic.error += 1
            return
        finally:
            self._statistic.done += 1

        # Validate that all results/exceptions are set by the func
        for item in items:
            if not item.future.done():
                item.future.set_exception(ResultNotSetError)

    def _set_exception(self, exc: Exception, items: list[Arg[V, R]]) -> None:
        for item in items:
            if not item.future.done():
                item.future.set_exception(exc)

    @staticmethod
    def _kwargs_key(kwargs: dict[str, Any]) -> frozenset[tuple[str, Any]]:
        try:
            return frozenset(kwargs.items())
        except TypeError as exc:
            raise TypeError(
                "Keyword arguments passed to an aggregated function "
                "must be hashable"
            ) from exc

    async def aggregate(self, arg: V, **kwargs: Any) -> R:
        key = self._kwargs_key(kwargs)
        bucket = self._buckets.get(key)
        if bucket is None:
            bucket = self._buckets[key] = Bucket()
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
            self._buckets.pop(key)
        else:
            # Waiting for max_count requests or a timeout
            try:
                await wait_for(
                    event.wait(),
                    timeout=first_call_at + self._leeway - self.loop.time(),
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

        # Clear only if not cleared already
        if self._buckets.get(key) is bucket:
            self._buckets.pop(key)

        # Trying to acquire the lock to execute the aggregated function
        async with lock:
            if not future.done():
                await self._execute(items=items, kwargs=kwargs)
        await future
        return future.result()


S = TypeVar("S", contravariant=True)
T = TypeVar("T", covariant=True)


class AggregateFunc(Protocol, Generic[S, T]):
    __name__: str

    async def __call__(self, *args: S, **kwargs: Any) -> Iterable[T]: ...


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
        func: Any,
        *,
        aggregator_class: type[AggregatorAsync[Any, Any]],
        leeway_ms: float,
        max_count: int | None,
    ) -> None:
        self._method: type[Any] | None
        if isinstance(func, classmethod):
            self._method = classmethod
            func = func.__func__
        elif isinstance(func, staticmethod):
            self._method = staticmethod
            func = func.__func__
        else:
            self._method = None

        if not _has_variadic_positional(func):
            raise ValueError(
                "Function must accept variadic positional arguments"
            )
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")
        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")

        functools.update_wrapper(self, func)
        self._func = func
        self._aggregator_class = aggregator_class
        self._leeway_ms = leeway_ms
        self._max_count = max_count
        self._plain: AggregatorAsync[Any, Any] | None = None
        self._cache_name = f"__aiomisc_aggregate_{id(self):x}"

    def _new(self, func: Any) -> AggregatorAsync[Any, Any]:
        return self._aggregator_class(
            func, leeway_ms=self._leeway_ms, max_count=self._max_count
        )

    def _get_plain(self) -> AggregatorAsync[Any, Any]:
        if self._plain is None:
            self._plain = self._new(self._func)
        return self._plain

    def _get_bound(self, receiver: Any) -> AggregatorAsync[Any, Any]:
        try:
            namespace = vars(receiver)
        except TypeError as exc:
            raise TypeError(
                "Aggregated methods require a writable __dict__"
            ) from exc

        aggregator = namespace.get(self._cache_name)
        if aggregator is not None:
            return aggregator

        owner = receiver if isinstance(receiver, type) else type(receiver)
        aggregator = self._new(self._func.__get__(receiver, owner))
        try:
            setattr(receiver, self._cache_name, aggregator)
        except (AttributeError, TypeError) as exc:
            raise TypeError(
                "Aggregated methods require a writable __dict__"
            ) from exc
        return aggregator

    def __call__(self, *args: Any, **kwargs: Any) -> Coroutine[Any, Any, R]:
        if len(args) == 1:
            return self._get_plain().aggregate(args[0], **kwargs)
        if len(args) == 2:
            return self._get_bound(args[0]).aggregate(args[1], **kwargs)
        raise TypeError("Aggregated functions accept one argument per call")

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if self._method is staticmethod:
            return self._get_plain().aggregate
        if self._method is classmethod:
            return self._get_bound(owner).aggregate
        if instance is None:
            return self
        return self._get_bound(instance).aggregate


def aggregate(
    leeway_ms: float, max_count: int | None = None
) -> Callable[..., AggregateDescriptor[V, R]]:
    """
    Parametric decorator that aggregates multiple
    (but no more than ``max_count`` defaulting to ``None``) single-argument
    executions (``res1 = await func(arg1)``, ``res2 = await func(arg2)``, ...)
    of an asynchronous function with variadic positional arguments
    (``async def func(*args, pho=1, bo=2) -> Iterable``) into its single
    execution with multiple positional arguments
    (``res1, res2, ... = await func(arg1, arg2, ...)``) collected within a time
    window ``leeway_ms``.

    Calls with different keyword arguments are batched separately; keyword
    values must be hashable. The decorator also supports instance, class, and
    static methods. Instances used with it must have a writable ``__dict__``.

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

    def decorator(func: Any) -> AggregateDescriptor[V, R]:
        return AggregateDescriptor(
            func,
            aggregator_class=Aggregator,
            max_count=max_count,
            leeway_ms=leeway_ms,
        )

    return decorator


def aggregate_async(
    leeway_ms: float, max_count: int | None = None
) -> Callable[..., AggregateDescriptor[V, R]]:
    """
    Same as ``aggregate``, but with ``func`` arguments of type ``Arg``
    containing ``value`` and ``future`` attributes instead. In this setting
    ``func`` is responsible for setting individual results/exceptions for all
    of the futures or throwing an exception (it will propagate to futures
    automatically). If ``func`` mistakenly does not set a result of some
    future, then, ``ResultNotSetError`` exception is set.

    :return:
    """

    def decorator(func: Any) -> AggregateDescriptor[V, R]:
        return AggregateDescriptor(
            func,
            aggregator_class=AggregatorAsync,
            max_count=max_count,
            leeway_ms=leeway_ms,
        )

    return decorator
