import asyncio
from functools import wraps
from typing import Any, Callable, Coroutine, ParamSpec, TypeVar, Union


T = TypeVar("T")
P = ParamSpec("P")
Number = Union[int, float]


def timeout(
    value: Number,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]],
    Callable[P, Coroutine[Any, Any, T]],
]:
    def decorator(
        func: Callable[P, Coroutine[Any, Any, T]],
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args: P.args, **kwargs: P.kwargs) -> T:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=value,
            )
        return wrap
    return decorator
