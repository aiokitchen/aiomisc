import asyncio
from functools import wraps
from time import monotonic
from typing import Optional, Type, TypeVar, Union

from .timeout import timeout


Number = Union[int, float]
T = TypeVar('T')


# noinspection PyPep8Naming,SpellCheckingInspection
class asyncbackoff:
    __slots__ = ('attempt_timeout', 'countdown', 'exceptions', 'pause')

    def __init__(self, attempt_timeout: Optional[Number],
                 deadline: Optional[Number],
                 pause: Number = 0, *exceptions: Type[Exception]):

        if pause < 0:
            raise ValueError("'pause' must be positive")

        if attempt_timeout is not None and attempt_timeout < 0:
            raise ValueError("'attempt_timeout' must be positive or None")

        if deadline is not None and deadline < 0:
            raise ValueError("'deadline' must be positive or None")

        self.exceptions = tuple(exceptions) or (Exception,)
        self.exceptions += asyncio.TimeoutError,
        self.pause = pause
        self.attempt_timeout = attempt_timeout
        self.countdown = deadline

    def __call__(self, func: T) -> T:
        if self.attempt_timeout is not None:
            func = timeout(self.attempt_timeout)(func)

        @wraps(func)
        async def wrap(*args, **kwargs):
            countdown = self.countdown
            pause = self.pause

            while countdown is None or countdown > 0:
                started_at = monotonic()

                try:
                    # noinspection PyCallingNonCallable
                    return await func(*args, **kwargs)
                except self.exceptions:
                    if countdown is not None:
                        countdown -= monotonic() - started_at + pause

                        if countdown <= 0:
                            raise

                    if pause > 0:
                        await asyncio.sleep(pause)

                    continue

            raise asyncio.TimeoutError('Is over now')

        return wrap
