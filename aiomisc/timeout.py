import asyncio
from functools import wraps
from typing import Union, TypeVar


Number = Union[int, float]
T = TypeVar('T')


class timeout:
    def __init__(self, timeout):
        self.timeout = timeout

    def __call__(self, func: T) -> T:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args, **kwargs):
            loop = asyncio.get_event_loop()

            # noinspection PyCallingNonCallable
            return await asyncio.wait_for(
                func(*args, **kwargs),
                self.timeout,
                loop=loop
            )   # type: asyncio.Task

        return wrap
