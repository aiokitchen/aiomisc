import asyncio
from functools import wraps
from typing import Union, TypeVar

from aiomisc.utils import cancel_tasks

Number = Union[int, float]
T = TypeVar('T')


def timeout(value):
    def decorator(func):
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args, **kwargs):
            loop = asyncio.get_event_loop()

            # noinspection PyCallingNonCallable
            done, pending = await asyncio.wait(
                [func(*args, **kwargs)],
                timeout=value,
                loop=loop,
                return_when=asyncio.FIRST_EXCEPTION,
            )   # type: asyncio.Task

            if done:
                return done.pop().result()

            await cancel_tasks(pending, loop=loop)
            raise asyncio.TimeoutError

        return wrap
    return decorator
