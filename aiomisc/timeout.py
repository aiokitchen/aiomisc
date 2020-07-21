import asyncio
from functools import wraps
from typing import Any

from .typehints import (
    CoroutineFunctionType as CCT,
    DecoratorType as DT, T, Number
)


def timeout(value: Number) -> DT[CCT[T]]:
    def decorator(func: CCT[T]) -> CCT[T]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args: Any, **kwargs: Any) -> Any:
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=value,
            )
        return wrap
    return decorator
