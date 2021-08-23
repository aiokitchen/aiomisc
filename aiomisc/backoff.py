import asyncio
from functools import wraps
from time import monotonic
from typing import (
    Any, Awaitable, Callable, Optional, Tuple, Type, TypeVar, Union,
)

from .counters import Statistic
from .timeout import timeout


Number = Union[int, float]
T = TypeVar("T")


WrapReturnType = Callable[[Callable[..., T]], T]
ReturnType = Callable[[Callable[..., T]], WrapReturnType]


class BackoffStatistic(Statistic):
    done: int
    attempts: int
    cancels: int
    errors: int
    sum_time: float


class RetryStatistic(BackoffStatistic):
    pass


# noinspection SpellCheckingInspection
def asyncbackoff(
    attempt_timeout: Optional[Number],
    deadline: Optional[Number],
    pause: Number = 0,
    *exc: Type[Exception], exceptions: Tuple[Type[Exception], ...] = (),
    max_tries: int = None,
    giveup: Callable[[Exception], bool] = None,
    statistic_name: Optional[str] = None,
    statistic_class: Type[BackoffStatistic] = BackoffStatistic
) -> ReturnType:
    """
    Patametric decorator that ensures that ``attempt_timeout`` and
    ``deadline`` time limits are met by decorated function.

    In case of exception function will be called again with similar
    arguments after ``pause`` seconds.

    :param statistic_name: name filed for statistic instances
    :param attempt_timeout: is maximum execution time for one
                            execution attempt.
    :param deadline: is maximum execution time for all execution attempts.
    :param pause: is time gap between execution attempts.
    :param exc: retrying when this exceptions was raised.
    :param exceptions: similar as exc but keyword only.
    :param max_tries: is maximum count of execution attempts (>= 1).
    :param giveup: is a predicate function which can decide by a given
    :param statistic_class: statistic class
    """

    exceptions = exc + tuple(exceptions)
    statistic = statistic_class(statistic_name)

    if not pause:
        pause = 0
    elif pause < 0:
        raise ValueError("'pause' must be positive")

    if attempt_timeout is not None and attempt_timeout < 0:
        raise ValueError("'attempt_timeout' must be positive or None")

    if deadline is not None and deadline < 0:
        raise ValueError("'deadline' must be positive or None")

    if max_tries is not None and max_tries < 1:
        raise ValueError("'max_retries' must be >= 1 or None")

    if giveup is not None and not callable(giveup):
        raise ValueError("'giveup' must be a callable or None")

    exceptions = tuple(exceptions) or ()
    exceptions += asyncio.TimeoutError,

    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> WrapReturnType:
        if attempt_timeout is not None:
            func = timeout(attempt_timeout)(func)

        @wraps(func)
        async def wrap(*args: Any, **kwargs: Any) -> Awaitable[T]:
            last_exc = None
            tries = 0

            async def run() -> Any:
                nonlocal last_exc, tries

                while True:
                    statistic.attempts += 1
                    tries += 1
                    delta = -monotonic()

                    try:
                        return await asyncio.wait_for(
                            func(*args, **kwargs),
                            timeout=attempt_timeout,
                        )
                    except asyncio.CancelledError:
                        statistic.cancels += 1
                        raise
                    except exceptions as e:
                        statistic.errors += 1
                        last_exc = e
                        if max_tries is not None and tries >= max_tries:
                            raise
                        if giveup and giveup(e):
                            raise
                        await asyncio.sleep(pause)
                    except Exception as e:
                        last_exc = e
                        raise
                    finally:
                        delta += monotonic()
                        statistic.sum_time += delta
                        statistic.done += 1

            try:
                return await asyncio.wait_for(run(), timeout=deadline)
            except Exception:
                if last_exc:
                    raise last_exc
                raise

        return wrap
    return decorator


def asyncretry(
    max_tries: Optional[int],
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    pause: Number = 0,
    giveup: Callable[[Exception], bool] = None,
    statistic_name: Optional[str] = None,
) -> ReturnType:
    """
    Shortcut of ``asyncbackoff(None, None, 0, Exception)``.

    In case of exception function will be called again with similar
    arguments after ``pause`` seconds.

    :param max_tries: is maximum count of execution attempts
                      (>= 1 or ``None`` means infinity).
    :param exceptions: similar as exc but keyword only.
    :param giveup: is a predicate function which can decide by a given
    :param pause: is time gap between execution attempts.
    :param statistic_name: name filed for statistic instances
    """

    return asyncbackoff(
        attempt_timeout=None,
        deadline=None,
        exceptions=exceptions,
        giveup=giveup,
        max_tries=max_tries,
        pause=pause,
        statistic_class=RetryStatistic,
        statistic_name=statistic_name,
    )
