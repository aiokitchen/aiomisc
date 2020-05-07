import asyncio
from functools import wraps
from typing import TypeVar, Union


Number = Union[int, float]
T = TypeVar("T")


def timeout(value):
    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args, **kwargs):
            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=value,
            )
        return wrap
    return decorator
