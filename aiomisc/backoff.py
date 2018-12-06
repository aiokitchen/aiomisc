import asyncio
from functools import wraps
from time import monotonic
from typing import Union, TypeVar, Type

from async_timeout import timeout

Number = Union[int, float]
T = TypeVar('T')


class asyncbackoff:
    __slots__ = ('countdown', 'exceptions', 'pause', 'waterline')

    def __init__(self, waterline: Number, deadline: Number,
                 pause: Number = 0, *exceptions: Type[Exception]):

        if pause < 0:
            raise ValueError("'pause' must be positive")

        if waterline < 0:
            raise ValueError("'waterline' must be positive")

        if deadline < 0:
            raise ValueError("'deadline' must be positive")

        self.exceptions = tuple(exceptions) or (Exception,)
        self.exceptions += asyncio.TimeoutError,
        self.pause = pause
        self.waterline = waterline
        self.countdown = deadline

    def __call__(self, func: T) -> T:
        if not asyncio.iscoroutinefunction(func):
            raise ValueError("Function is not a coroutine function")

        @wraps(func)
        async def wrap(*args, **kwargs):
            while self.countdown > 0:
                started_at = monotonic()

                try:
                    async with timeout(self.waterline):
                        # noinspection PyCallingNonCallable
                        return await func(*args, **kwargs)
                except self.exceptions:
                    self.countdown -= monotonic() - started_at + self.pause

                    if self.countdown <= 0:
                        raise
                    elif self.pause > 0:
                        await asyncio.sleep(self.pause)

                    continue

            raise asyncio.TimeoutError('Is over now')

        return wrap
