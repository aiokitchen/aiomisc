import asyncio
from functools import wraps
from typing import Optional, Type, TypeVar, Union

from .timeout import timeout


Number = Union[int, float]
T = TypeVar('T')


# noinspection SpellCheckingInspection
def asyncbackoff(attempt_timeout: Optional[Number],
                 deadline: Optional[Number], pause: Number = 0,
                 *exc: Type[Exception], exceptions=()):

    exceptions = exc + tuple(exceptions)

    if not pause:
        pause = 0
    elif pause < 0:
        raise ValueError("'pause' must be positive")

    if attempt_timeout is not None and attempt_timeout < 0:
        raise ValueError("'attempt_timeout' must be positive or None")

    if deadline is not None and deadline < 0:
        raise ValueError("'deadline' must be positive or None")

    exceptions = tuple(exceptions) or ()
    exceptions += asyncio.TimeoutError,

    def decorator(func):
        if attempt_timeout is not None:
            func = timeout(attempt_timeout)(func)

        @wraps(func)
        async def wrap(*args, **kwargs):
            loop = asyncio.get_event_loop()
            last_exc = None

            async def run():
                nonlocal last_exc

                while True:
                    try:
                        return await asyncio.wait_for(
                            func(*args, **kwargs),
                            loop=loop,
                            timeout=attempt_timeout
                        )
                    except asyncio.CancelledError:
                        raise
                    except exceptions as e:
                        last_exc = e
                        await asyncio.sleep(pause, loop=loop)

            try:
                return await asyncio.wait_for(
                    run(), timeout=deadline, loop=loop
                )
            except Exception:
                if last_exc:
                    raise last_exc
                raise

        return wrap
    return decorator
