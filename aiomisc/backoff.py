import asyncio
from functools import wraps
from time import monotonic
from typing import Optional, Type, TypeVar, Union

from .timeout import timeout


Number = Union[int, float]
T = TypeVar('T')


# noinspection SpellCheckingInspection
def asyncbackoff(attempt_timeout: Optional[Number],
                 deadline: Optional[Number],
                 pause: Number = 0, *exceptions: Type[Exception]):
    if pause < 0:
        raise ValueError("'pause' must be positive")

    if attempt_timeout is not None and attempt_timeout < 0:
        raise ValueError("'attempt_timeout' must be positive or None")

    if deadline is not None and deadline < 0:
        raise ValueError("'deadline' must be positive or None")

    exceptions = tuple(exceptions) or (Exception,)
    exceptions += asyncio.TimeoutError,

    def decorator(func):
        if attempt_timeout is not None:
            func = timeout(attempt_timeout)(func)

        @wraps(func)
        async def wrap(*args, **kwargs):
            countdown = deadline

            while countdown is None or countdown > 0:
                started_at = monotonic()

                try:
                    # noinspection PyCallingNonCallable
                    return await func(*args, **kwargs)
                except exceptions:
                    if countdown is not None:
                        countdown -= monotonic() - started_at + pause

                        if countdown <= 0:
                            raise

                    if pause > 0:
                        await asyncio.sleep(pause)

                    continue

            raise asyncio.TimeoutError('Is over now')
        return wrap
    return decorator
