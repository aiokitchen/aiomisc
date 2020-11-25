import asyncio
import inspect
from asyncio import Future, Event, Lock, CancelledError, wait_for
from contextlib import suppress
from inspect import Parameter
from time import monotonic
from typing import List, Optional, Callable, Any, Awaitable, Iterable

AggFunc = Callable[[Any], Awaitable[Iterable]]


class Aggregator:

    def __init__(
            self, func: AggFunc, *,
            leeway_ms: float, max_count: int = None,
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

        self._func = func
        self._max_count = max_count
        self._leeway = leeway_ms / 1000
        self._t = None          # type: Optional[float]
        self._args = []         # type: list
        self._futures = []      # type: List[Future]
        self._event = Event()   # type: Event
        self._lock = Lock()     # type: Lock

    @property
    def max_count(self) -> Optional[int]:
        return self._max_count

    @property
    def leeway_ms(self) -> float:
        return self._leeway * 1000

    @property
    def count(self) -> int:
        return len(self._args)

    def _clear(self) -> None:
        self._t = None
        self._args = []
        self._futures = []
        self._event = Event()
        self._lock = Lock()

    async def _execute(self, *, args: list, futures: List[Future]) -> None:
        try:
            results = await self._func(*args)
        except CancelledError:
            # Other waiting tasks can try to finish the job instead.
            raise
        except Exception as e:
            self._set_exception(e, futures)
            return

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
        if not self._t:
            self._t = monotonic()
        t = self._t

        args = self._args           # type: List
        futures = self._futures     # type: List
        event = self._event         # type: Event
        lock = self._lock           # type: Lock
        args.append(arg)
        future = Future()           # type: Future
        futures.append(future)

        if self.count == self.max_count:
            event.set()
            self._clear()
        else:
            # Waiting for max_count requests or a timeout
            with suppress(asyncio.TimeoutError):
                await wait_for(
                    event.wait(),
                    timeout=t + self._leeway - monotonic(),
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


def aggregate(leeway_ms: float, max_count: int = None) -> Callable:
    """
    Parametric decorator that aggregates multiple
    (but no more than ``max_count``) single-argument executions
    (``res1 = func(arg1)``, ``res2 = func(arg2)``, ...)
    of the function with variadic positional arguments
    (``def func(*args, pho=1, bo=2) -> Iterable``)
    into its single execution with multiple positional arguments
    (``res1, res2, ... = func(arg1, arg2, ...)``) collected within a time
    window ``leeway_ms``.
    :param leeway_ms: The maximum approximate delay between the first
    collected argument and the aggregated execution.
    :param max_count: The maximum number of arguments to call decorated
    function with. Default ``None``.
    :return:
    """
    def decorator(func: AggFunc) -> Any:
        aggregator = Aggregator(func, max_count=max_count, leeway_ms=leeway_ms)

        async def wrap(arg: Any) -> Any:
            return await aggregator.aggregate(arg)
        return wrap

    return decorator
