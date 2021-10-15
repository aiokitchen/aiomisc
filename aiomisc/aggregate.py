import asyncio
import inspect
import logging
from asyncio import CancelledError, Event, Future, Lock, wait_for
from inspect import Parameter
from typing import (
    Any, Awaitable, Callable, Iterable, List, NamedTuple, Optional, Union,
)

from .counters import Statistic


log = logging.getLogger(__name__)


class Arg(NamedTuple):
    value: Any
    future: Future


class ResultNotSetError(Exception):
    pass


AggFuncHighLevel = Callable[[Any], Awaitable[Iterable]]
AggFuncAsync = Callable[[Arg], Awaitable]
AggFunc = Union[AggFuncHighLevel, AggFuncAsync]


class AggregateStatistic(Statistic):
    leeway_ms: float
    max_count: int
    success: int
    error: int
    done: int


class Aggregator:

    _func: AggFunc
    _max_count: Optional[int]
    _leeway: float
    _first_call_at: Optional[float]
    _args: list
    _futures: List[Future]
    _event: Event
    _lock: Lock

    def __init__(
        self, func: AggFunc, *, leeway_ms: float,
        max_count: Optional[int] = None,
        statistic_name: Optional[str] = None
    ):
        has_variadic_positional = any((
            parameter.kind == Parameter.VAR_POSITIONAL
            for parameter in inspect.signature(func).parameters.values()
        ))
        if not has_variadic_positional:
            raise ValueError(
                "Function must accept variadic positional arguments",
            )

        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be positive int or None")

        if leeway_ms <= 0:
            raise ValueError("leeway_ms must be positive float")

        self._loop = asyncio.get_event_loop()
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

    async def _execute(self, *, args: list, futures: List[Future]) -> None:
        try:
            results = await self._func(*args)
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

        self._set_results(results, futures)

    def _set_results(self, results: Iterable, futures: List[Future]) -> None:
        for future, result in zip(futures, results):
            if not future.done():
                future.set_result(result)

    def _set_exception(
            self, exc: Exception, futures: List[Future],
    ) -> None:
        for future in futures:
            if not future.done():
                future.set_exception(exc)

    async def aggregate(self, arg: Any) -> Any:
        if self._first_call_at is None:
            self._first_call_at = self._loop.time()
        first_call_at = self._first_call_at

        args: list = self._args
        futures: List[Future] = self._futures
        event: Event = self._event
        lock: Lock = self._lock
        args.append(arg)
        future: Future = Future()
        futures.append(future)

        if self.count == self.max_count:
            event.set()
            self._clear()
        else:
            # Waiting for max_count requests or a timeout
            try:
                await wait_for(
                    event.wait(),
                    timeout=first_call_at + self._leeway - self._loop.time(),
                )
            except asyncio.TimeoutError:
                log.debug(
                    "Aggregation timeout of %s for batch started at %.4f "
                    "with %d calls after %.2f ms",
                    self._func.__name__, first_call_at, len(futures),
                    (self._loop.time() - first_call_at) * 1000,
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


class AggregatorAsync(Aggregator):

    async def _execute(self, *, args: list, futures: List[Future]) -> None:
        args = [
            Arg(value=arg, future=future)
            for arg, future in zip(args, futures)
        ]
        try:
            await self._func(*args)
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


def aggregate(leeway_ms: float, max_count: Optional[int] = None) -> Callable:
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
    def decorator(func: AggFuncHighLevel) -> Callable[[Any], Awaitable]:
        aggregator = Aggregator(
            func, max_count=max_count, leeway_ms=leeway_ms,
        )
        return aggregator.aggregate
    return decorator


def aggregate_async(
        leeway_ms: float, max_count: Optional[int] = None,
) -> Callable:
    """
    Same as ``aggregate``, but with ``func`` arguments of type ``Arg``
    containing ``value`` and ``future`` attributes instead. In this setting
    ``func`` is responsible for setting individual results/exceptions for all
    of the futures or throwing an exception (it will propagate to futures
    automatically). If ``func`` mistakenly does not set a result of some
    future, then, ``ResultNotSetError`` exception is set.

    :return:
    """
    def decorator(func: AggFuncAsync) -> Callable[[Any], Awaitable]:
        aggregator = AggregatorAsync(
            func, max_count=max_count, leeway_ms=leeway_ms,
        )
        return aggregator.aggregate
    return decorator
