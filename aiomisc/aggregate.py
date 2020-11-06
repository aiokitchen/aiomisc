import inspect
from asyncio import Future, wait
from inspect import Parameter
from time import monotonic
from typing import List, Optional, Callable, Any, Awaitable

AggFunc = Callable[[...], Awaitable]


class Aggregator:

    def __init__(
            self, func: AggFunc, *,
            max_count: int, leeway_ms: float,
    ):
        has_variadic_positional = any((
            parameter.kind == Parameter.VAR_POSITIONAL
            for parameter in inspect.signature(func).parameters.values()
        ))
        if not has_variadic_positional:
            raise ValueError(
                'Function must accept variadic positional arguments',
            )

        if max_count <= 0:
            raise ValueError('max_count must be positive int')

        if leeway_ms < 0:
            raise ValueError('leeway_ms must be non-negative float')

        self._func = func
        self._max_count = max_count
        self._leeway = leeway_ms / 1000
        self._t = None      # type: Optional[float]
        self._args = []     # type: list
        self._futures = []  # type: List[Future]

    @property
    def max_count(self) -> int:
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

    async def _execute(self) -> None:
        futures, args = self._futures, self._args
        self._clear()
        try:
            results = await self._func(*args)
        except Exception as e:
            for future in futures:
                future.set_exception(e)
            return

        for future, result in zip(futures, results):
            future.set_result(result)

    async def aggregate(self, arg: Any) -> Any:
        if not self._t:
            self._t = monotonic()

        self._args.append(arg)
        future = Future()
        first = not self._futures
        self._futures.append(future)

        if self.count == self.max_count:
            await self._execute()

        if first:
            timeout = self._t + self._leeway - monotonic()
            done, pending = await wait([future], timeout=timeout)
            if pending:
                await self._execute()

        await future
        return future.result()


def aggregate(max_count: int, leeway_ms: float):
    def outer(func: AggFunc) -> Any:
        aggregator = Aggregator(func, max_count=max_count, leeway_ms=leeway_ms)

        async def inner(arg: Any) -> Any:
            return await aggregator.aggregate(arg)
        return inner

    return outer
