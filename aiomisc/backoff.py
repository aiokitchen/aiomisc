import asyncio
from functools import wraps
from time import monotonic
from typing import Optional, Type, TypeVar, Union

from .timeout import timeout


Number = Union[int, float]
T = TypeVar('T')


class asyncbackoff:
    __slots__ = ('countdown', 'exceptions', 'pause', 'waterline')

    def __init__(self, waterline: Optional[Number],
                 deadline: Optional[Number],
                 pause: Number = 0, *exceptions: Type[Exception]):

        if pause < 0:
            raise ValueError("'pause' must be positive")

        if waterline is not None and waterline < 0:
            raise ValueError("'waterline' must be positive or None")

        if deadline is not None and deadline < 0:
            raise ValueError("'deadline' must be positive or None")

        self.exceptions = tuple(exceptions) or (Exception,)
        self.exceptions += asyncio.TimeoutError,
        self.pause = pause
        self.waterline = waterline
        self.countdown = deadline

    def __call__(self, func: T) -> T:
        if self.waterline is not None:
            func = timeout(self.waterline)(func)

        @wraps(func)
        async def wrap(*args, **kwargs):
            while self.countdown is None or self.countdown > 0:
                started_at = monotonic()

                try:
                    # noinspection PyCallingNonCallable
                    return await func(*args, **kwargs)
                except self.exceptions:
                    if self.countdown is not None:
                        self.countdown -= monotonic() - started_at + self.pause

                        if self.countdown <= 0:
                            raise

                    if self.pause > 0:
                        await asyncio.sleep(self.pause)

                    continue

            raise asyncio.TimeoutError('Is over now')

        return wrap
