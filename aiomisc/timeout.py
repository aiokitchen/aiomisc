import asyncio
from functools import wraps
from typing import Any, Awaitable, Callable, TypeVar, Union


T = TypeVar("T")
Number = Union[int, float]
FuncType = Callable[..., Awaitable[T]]


def timeout(value: Number) -> Callable[[FuncType], FuncType]:
    def decorator(
        func: FuncType,
    ) -> FuncType:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args: Any, **kwargs: Any) -> T:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=value,
            )
        return wrap
    return decorator
