import asyncio
import functools
import inspect
import logging
import weakref
from asyncio import CancelledError, Event, Future, Lock
from collections.abc import Callable, Coroutine, Iterable
from dataclasses import dataclass, field
from inspect import Parameter
from typing import Any, Generic, Protocol, TypeVar, overload

from .compat import EventLoopMixin
from .counters import Statistic

log = logging.getLogger(__name__)


V = TypeVar("V")
R = TypeVar("R")


@dataclass(frozen=True)
class Arg(Generic[V, R]):
    value: V
    future: Future[R]


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


def _validate(
    func: Callable[..., Any], leeway_ms: float, max_count: int | None
) -> None:
    if not _has_variadic_positional(func):
        raise ValueError("Function must accept variadic positional arguments")
    if max_count is not None and max_count <= 0:
        raise ValueError("max_count must be positive int or None")
    if leeway_ms <= 0:
        raise ValueError("leeway_ms must be positive float")


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
        _validate(func, leeway_ms, max_count)

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
        item = Arg(value=arg, future=future)
        items.append(item)

        if len(items) == self.max_count:
            event.set()
            self._buckets.pop(key)
        else:
            # Waiting for max_count requests or a timeout
            try:
                async with asyncio.timeout_at(first_call_at + self._leeway):
                    await event.wait()
            except TimeoutError:
                log.debug(
                    "Aggregation timeout of %s for batch started at %.4f "
                    "with %d calls after %.2f ms",
                    self._func.__name__,
                    first_call_at,
                    len(items),
                    (self.loop.time() - first_call_at) * 1000,
                )
            except CancelledError:
                future.cancel()
                if self._buckets.get(key) is bucket:
                    items[:] = [entry for entry in items if entry is not item]
                    if not items:
                        self._buckets.pop(key)
                raise

        # Clear only if not cleared already
        if self._buckets.get(key) is bucket:
            self._buckets.pop(key)

        # Trying to acquire the lock to execute the aggregated function
        try:
            async with lock:
                if not future.done():
                    await self._execute(items=items, kwargs=kwargs)
            await future
        except CancelledError:
            future.cancel()
            raise
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
        super().__init__(
            _to_async_aggregate(func),
            leeway_ms=leeway_ms,
            max_count=max_count,
            statistic_name=statistic_name,
        )


class _BoundAggregate:
    def __init__(self) -> None:
        self.owner: Callable[[], Any] = lambda: None
        self.call: Any = None

    def __reduce__(self) -> tuple[Any, tuple[()]]:
        # Cached batches belong to one owner and are never copied or pickled.
        return type(self), ()


def _bind_call(call: Any, receiver: Any) -> Any:
    @functools.wraps(call)
    async def bound_call(arg: Any, **kwargs: Any) -> Any:
        # Keep temporary owners alive until the batch finishes.
        _owner = receiver
        return await call(arg, **kwargs)

    return bound_call


class _AggregateCall(Protocol[V, R]):
    __self__: AggregatorAsync[V, R]

    def __call__(self, arg: V, **kwargs: Any) -> Coroutine[Any, Any, R]: ...


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

        _validate(func, leeway_ms, max_count)

        functools.update_wrapper(self, func)
        self._func = func
        self._aggregator_class = aggregator_class
        self._leeway_ms = leeway_ms
        self._max_count = max_count
        self._plain: AggregatorAsync[Any, Any] | None = None
        self._cache_name = (
            f"__aiomisc_aggregate_{func.__module__}.{func.__qualname__}"
        )
        self._in_class = False
        # Python 3.11 uses these attributes to recognize async callables.
        self.__code__ = self.__call__.__code__
        self.__defaults__ = None
        self.__kwdefaults__ = None
        if hasattr(inspect, "markcoroutinefunction"):
            inspect.markcoroutinefunction(self)

    def __set_name__(self, owner: type, name: str) -> None:
        self._in_class = True
        self._cache_name = f"__aiomisc_aggregate_{owner.__module__}.{owner.__qualname__}.{name}"

    @property
    def __self__(self) -> AggregatorAsync[V, R]:
        return self._get_plain()

    def _new(self, func: Any) -> AggregatorAsync[Any, Any]:
        return self._aggregator_class(
            func, leeway_ms=self._leeway_ms, max_count=self._max_count
        )

    def _get_plain(self) -> AggregatorAsync[Any, Any]:
        if self._plain is None:
            self._plain = self._new(self._func)
        return self._plain

    def _get_bound(
        self, receiver: Any
    ) -> Callable[..., Coroutine[Any, Any, R]]:
        try:
            namespace = vars(receiver)
        except TypeError as exc:
            raise TypeError(
                "Aggregated methods require a writable __dict__"
            ) from exc

        cached = namespace.get(self._cache_name)
        if isinstance(cached, _BoundAggregate) and cached.owner() is receiver:
            return _bind_call(cached.call, receiver)

        owner = receiver if isinstance(receiver, type) else type(receiver)
        bound = self._func.__get__(receiver, owner)
        cached = _BoundAggregate()
        try:
            cached.owner = weakref.ref(receiver)
            method = weakref.WeakMethod(bound)

            @functools.wraps(self._func)
            async def invoke(*args: Any, **kwargs: Any) -> Any:
                func = method()
                if func is None:
                    raise ReferenceError(
                        "Aggregated method owner no longer exists"
                    )
                return await func(*args, **kwargs)

            setattr(invoke, "__signature__", inspect.signature(bound))
            aggregator = self._new(invoke)
        except TypeError:
            cached.owner = lambda: receiver
            aggregator = self._new(bound)

        @functools.wraps(self._func)
        async def call(arg: V, **kwargs: Any) -> R:
            return await aggregator.aggregate(arg, **kwargs)

        setattr(call, "__signature__", inspect.signature(bound))
        setattr(call, "__self__", aggregator)
        cached.call = call
        try:
            setattr(receiver, self._cache_name, cached)
        except (AttributeError, TypeError) as exc:
            raise TypeError(
                "Aggregated methods require a writable __dict__"
            ) from exc
        return _bind_call(call, receiver)

    @overload
    def __call__(self, arg: V, **kwargs: Any) -> Coroutine[Any, Any, R]: ...

    @overload
    def __call__(
        self, receiver: object, arg: V, **kwargs: Any
    ) -> Coroutine[Any, Any, R]: ...

    async def __call__(self, *args: Any, **kwargs: Any) -> R:
        if len(args) == 1:
            if self._in_class and self._method is not staticmethod:
                raise TypeError(
                    "Unbound aggregated methods require an instance and one argument"
                )
            return await self._get_plain().aggregate(args[0], **kwargs)
        if len(args) == 2:
            return await self._get_bound(args[0])(args[1], **kwargs)
        raise TypeError("Aggregated functions accept one argument per call")

    @overload
    def __get__(
        self, instance: None, owner: type | None = None
    ) -> "AggregateDescriptor[V, R]": ...

    @overload
    def __get__(
        self, instance: object, owner: type | None = None
    ) -> _AggregateCall[Any, R]: ...

    def __get__(self, instance: Any, owner: type | None = None) -> Any:
        if self._method is staticmethod:
            return self
        if self._method is classmethod:
            return self._get_bound(owner)
        if instance is None:
            return self
        return self._get_bound(instance)


class _AggregatePlainFunc(Protocol[S, T]):
    def __call__(self, *args: S) -> Coroutine[Any, Any, Iterable[T]]: ...


class _AggregateAsyncPlainFunc(Protocol[V, R]):
    def __call__(self, *args: Arg[V, R]) -> Coroutine[Any, Any, None]: ...


class _AggregateDecorator(Protocol):
    @overload
    def __call__(
        self, func: _AggregatePlainFunc[V, R]
    ) -> AggregateDescriptor[V, R]: ...

    @overload
    def __call__(
        self, func: AggregateFunc[V, R]
    ) -> AggregateDescriptor[V, R]: ...

    @overload
    def __call__(
        self, func: Callable[..., Coroutine[Any, Any, Iterable[R]]]
    ) -> AggregateDescriptor[Any, R]: ...

    @overload
    def __call__(
        self, func: "classmethod[Any, Any, Any] | staticmethod[Any, Any]"
    ) -> AggregateDescriptor[Any, Any]: ...


class _AggregateAsyncDecorator(Protocol):
    @overload
    def __call__(
        self, func: _AggregateAsyncPlainFunc[V, R]
    ) -> AggregateDescriptor[V, R]: ...

    @overload
    def __call__(
        self, func: AggregateAsyncFunc[V, R]
    ) -> AggregateDescriptor[V, R]: ...

    @overload
    def __call__(
        self,
        func: "Callable[..., Coroutine[Any, Any, None]] | classmethod[Any, Any, Any] | staticmethod[Any, Any]",
    ) -> AggregateDescriptor[Any, Any]: ...


def aggregate(
    leeway_ms: float, max_count: int | None = None
) -> _AggregateDecorator:
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

    def decorator(func: Any) -> AggregateDescriptor[Any, Any]:
        return AggregateDescriptor(
            func,
            aggregator_class=Aggregator,
            max_count=max_count,
            leeway_ms=leeway_ms,
        )

    return decorator


def aggregate_async(
    leeway_ms: float, max_count: int | None = None
) -> _AggregateAsyncDecorator:
    """
    Same as ``aggregate``, but with ``func`` arguments of type ``Arg``
    containing ``value`` and ``future`` attributes instead. In this setting
    ``func`` is responsible for setting individual results/exceptions for all
    of the futures or throwing an exception (it will propagate to futures
    automatically). If ``func`` mistakenly does not set a result of some
    future, then, ``ResultNotSetError`` exception is set.

    :return:
    """

    def decorator(func: Any) -> AggregateDescriptor[Any, Any]:
        return AggregateDescriptor(
            func,
            aggregator_class=AggregatorAsync,
            max_count=max_count,
            leeway_ms=leeway_ms,
        )

    return decorator
