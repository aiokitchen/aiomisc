import asyncio
from functools import wraps
from typing import Union, TypeVar


Number = Union[int, float]
T = TypeVar('T')


def timeout(value):
    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args, **kwargs):
            loop = asyncio.get_event_loop()

            return await asyncio.wait_for(
                func(*args, **kwargs),
                timeout=value,
                loop=loop,
            )
        return wrap
    return decorator
