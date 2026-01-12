import asyncio
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, Generic, ParamSpec, TypeVar

from .counters import Statistic

Number = int | float
T = TypeVar("T")
P = ParamSpec("P")


class BackoffStatistic(Statistic):
    done: int
    attempts: int
    cancels: int
    errors: int
    sum_time: float


class RetryStatistic(BackoffStatistic):
    pass


class Backoff:
    __slots__ = (
        "attempt_timeout",
        "deadline",
        "exceptions",
        "giveup",
        "max_tries",
        "pause",
        "statistic",
    )

    def __init__(
        self,
        attempt_timeout: Number | None,
        deadline: Number | None,
        pause: Number = 0,
        exceptions: tuple[type[Exception], ...] = (),
        max_tries: int | None = None,
        giveup: Callable[[Exception], bool] | None = None,
        statistic_name: str | None = None,
        statistic_class: type[BackoffStatistic] = BackoffStatistic,
    ):
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
        exceptions += (asyncio.TimeoutError,)

        self.attempt_timeout = attempt_timeout
        self.deadline = deadline
        self.pause = pause
        self.max_tries = max_tries
        self.giveup = giveup
        self.exceptions = exceptions
        self.statistic = statistic_class(statistic_name)

    def prepare(
        self, func: Callable[P, Coroutine[Any, Any, T]]
    ) -> "BackoffExecution[P, T]":
        return BackoffExecution(
            function=func,
            statistic=self.statistic,
            attempt_timeout=self.attempt_timeout,
            deadline=self.deadline,
            pause=self.pause,
            max_tries=self.max_tries,
            giveup=self.giveup,
            exceptions=self.exceptions,
        )

    async def execute(
        self,
        func: Callable[P, Coroutine[Any, Any, T]],
        *args: P.args,
        **kwargs: P.kwargs,
    ) -> T:
        execution = self.prepare(func)
        return await execution(*args, **kwargs)

    def __call__(
        self, func: Callable[P, Coroutine[Any, Any, T]]
    ) -> Callable[P, Coroutine[Any, Any, T]]:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function must be a coroutine function")

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await self.execute(func, *args, **kwargs)

        return wrapper


class BackoffExecution(Generic[P, T]):
    __slots__ = (
        "attempt_timeout",
        "deadline",
        "exceptions",
        "function",
        "giveup",
        "last_exception",
        "max_tries",
        "pause",
        "statistic",
        "total_tries",
    )

    def __init__(
        self,
        function: Callable[P, Coroutine[Any, Any, T]],
        statistic: BackoffStatistic,
        attempt_timeout: Number | None,
        deadline: Number | None,
        pause: Number = 0,
        exceptions: tuple[type[Exception], ...] = (),
        max_tries: int | None = None,
        giveup: Callable[[Exception], bool] | None = None,
    ):
        self.function = function
        self.statistic = statistic
        self.attempt_timeout = attempt_timeout
        self.deadline = deadline
        self.pause = pause
        self.max_tries = max_tries
        self.giveup = giveup
        self.exceptions = exceptions

        self.last_exception: Exception | None = None
        self.total_tries: int = 0

    async def __call__(self, *args: P.args, **kwargs: P.kwargs) -> T:
        return await self.execute(*args, **kwargs)

    async def execute(self, *args: P.args, **kwargs: P.kwargs) -> T:
        async def run() -> Any:
            loop = asyncio.get_running_loop()

            while True:
                self.statistic.attempts += 1
                self.total_tries += 1
                delta = -loop.time()

                try:
                    return await asyncio.wait_for(
                        self.function(*args, **kwargs),
                        timeout=self.attempt_timeout,
                    )
                except asyncio.CancelledError:
                    self.statistic.cancels += 1
                    raise
                except self.exceptions as e:
                    self.statistic.errors += 1
                    self.last_exception = e
                    if (
                        self.max_tries is not None
                        and self.total_tries >= self.max_tries
                    ):
                        raise

                    if self.giveup and self.giveup(e):
                        raise
                    await asyncio.sleep(self.pause)
                except Exception as e:
                    self.last_exception = e
                    raise
                finally:
                    delta += loop.time()
                    self.statistic.sum_time += delta
                    self.statistic.done += 1

        try:
            return await asyncio.wait_for(run(), timeout=self.deadline)
        except Exception:
            if self.last_exception is not None:
                raise self.last_exception
            raise


# noinspection SpellCheckingInspection
def asyncbackoff(
    attempt_timeout: Number | None,
    deadline: Number | None,
    pause: Number = 0,
    *exc: type[Exception],
    exceptions: tuple[type[Exception], ...] = (),
    max_tries: int | None = None,
    giveup: Callable[[Exception], bool] | None = None,
    statistic_name: str | None = None,
    statistic_class: type[BackoffStatistic] = BackoffStatistic,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]:
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
    :param exc: retrying when these exceptions were raised.
    :param exceptions: similar as exc but keyword only.
    :param max_tries: is maximum count of execution attempts (>= 1).
    :param giveup: is a predicate function which can decide by a given
    :param statistic_class: statistic class
    """

    return Backoff(
        attempt_timeout=attempt_timeout,
        deadline=deadline,
        pause=pause,
        exceptions=exceptions or exc,
        max_tries=max_tries,
        giveup=giveup,
        statistic_name=statistic_name,
        statistic_class=statistic_class,
    )


def asyncretry(
    max_tries: int | None,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    pause: Number = 0,
    giveup: Callable[[Exception], bool] | None = None,
    statistic_name: str | None = None,
) -> Callable[
    [Callable[P, Coroutine[Any, Any, T]]], Callable[P, Coroutine[Any, Any, T]]
]:
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
