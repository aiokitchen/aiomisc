import asyncio
import threading
import typing
from collections import Counter, deque
from contextlib import contextmanager
from enum import IntEnum, unique
from functools import wraps
from random import random

from aiomisc.utils import awaitable


TimeType = typing.Union[int, float]
StatisticType = typing.Deque[typing.Tuple[int, Counter]]


@unique
class CounterKey(IntEnum):
    FAIL = 0
    OK = 1
    TOTAL = 2


@unique
class CircuitBreakerStates(IntEnum):
    PASSING = 0
    BROKEN = 1
    RECOVERING = 2


class CircuitBroken(Exception):
    pass


class CircuitBreaker:
    __slots__ = (
        "_broken_time",
        "_error_ratio",
        "_exceptions",
        "_lock",
        "_loop",
        "_passing_time",
        "_recovery_at",
        "_recovery_ratio",
        "_recovery_time",
        "_response_time",
        "_state",
        "_statistic",
        "_stuck_until",
    )

    BUCKET_COUNT = 10
    # Thresholds when state will be changed

    # * RECOVER state will be changed to BROKEN
    #   when error ratio will be greater or equal then
    #   RECOVER_BROKEN_THRESHOLD
    RECOVER_BROKEN_THRESHOLD = 0.5
    # * PASSING state will be changed to BROKEN
    #   when error ratio will be greater or equal then
    #   PASSING_BROKEN_THRESHOLD
    PASSING_BROKEN_THRESHOLD = 1

    def __init__(
        self,
        error_ratio: float,
        response_time: TimeType,
        exceptions: typing.Iterable[typing.Type[Exception]] = (Exception,),
        recovery_time: TimeType = None,
        broken_time: TimeType = None,
        passing_time: TimeType = None
    ):
        """
        Circuit Breaker pattern implementation. The class instance collects
        call statistics through the ``call`` or ``call async`` methods.

        The state machine has three states:
        * ``CircuitBreakerStates.PASSING``
        * ``CircuitBreakerStates.BROKEN``
        * ``CircuitBreakerStates.RECOVERING``

        In passing mode all results or exceptions will be returned as is.
        Statistic collects for each call.

        In broken mode returns exception ``CircuitBroken`` for each call.
        Statistic doesn't collecting.

        In recovering mode the part of calls is real function calls and
        remainings raises ``CircuitBroken``. The count of real calls grows
        exponentially in this case but when 20% (by default) will be failed
        the state returns to broken state.

        :param error_ratio: Failed to success calls ratio. The state might be
                            changed if ratio will reach given value within
                            ``response time`` (in seconds).
                            Value between 0.0 and 1.0.
        :param response_time: Time window to collect statistics (seconds)
        :param exceptions: Only this exceptions will affect ratio.
                           Base class  ``Exception`` used by default.
        :param recovery_time: minimal time in recovery state (seconds)
        :param broken_time: minimal time in broken state (seconds)
        :param passing_time: minimum time in passing state (seconds)
        """
        if response_time <= 0:
            raise ValueError("Response time must be greater then zero")

        if 0. > error_ratio >= 1.:
            raise ValueError(
                "Error ratio must be between 0 and 1 not %r" % error_ratio
            )

        self._statistic = deque(
            maxlen=self.BUCKET_COUNT
        )  # type: StatisticType
        self._lock = threading.RLock()
        self._loop = asyncio.get_event_loop()
        self._error_ratio = error_ratio
        self._state = CircuitBreakerStates.PASSING
        self._response_time = response_time
        self._stuck_until = 0
        self._recovery_at = 0

        self._exceptions = tuple(frozenset(exceptions))

        self._passing_time = passing_time or self._response_time
        self._broken_time = broken_time or self._response_time
        self._recovery_time = recovery_time or self._response_time

    @property
    def response_time(self) -> TimeType:
        return self._response_time

    @property
    def state(self) -> CircuitBreakerStates:
        return self._state

    def _get_time(self) -> float:
        return self._loop.time()

    def bucket(self) -> int:
        ts = self._get_time() * self.BUCKET_COUNT
        return int(ts - (ts % self._response_time))

    def counter(self) -> Counter:
        with self._lock:
            current = self.bucket()

            if not self._statistic:
                # Empty statistic just return a new counter
                counter = Counter()
                self._statistic.append((current, counter))
                return counter

            bucket, counter = self._statistic[-1]

            if current != bucket:
                # Append Counter to statistic or shift when maxsize reached
                counter = Counter()
                self._statistic.append((current, counter))

            return counter

    def __gen_statistic(self) -> typing.Generator[Counter, None, None]:
        """
        Generator which returns only buckets Counters not before current_time
        """
        not_before = self.bucket() - (self._response_time * self.BUCKET_COUNT)

        for idx in range(len(self._statistic) - 1, -1, -1):
            bucket, counter = self._statistic[idx]

            if bucket < not_before:
                break

            yield counter

    def get_state_delay(self):
        delay = self._stuck_until - self._get_time()
        return max(delay, 0)

    def _on_passing(self, counter):
        try:
            yield
            counter[CounterKey.OK] += 1
        except self._exceptions:
            counter[CounterKey.FAIL] += 1
            raise
        finally:
            counter[CounterKey.TOTAL] += 1

    def _on_broken(self):
        raise CircuitBroken()

    def _on_recover(self, counter):
        current_time = self._get_time()
        condition = (random() + 1) < (
            2 ** ((current_time - self._recovery_at) / self._recovery_time)
        )

        if not condition:
            raise CircuitBroken()

        yield from self._on_passing(counter)

    @property
    def recovery_ratio(self):
        total_count = 0
        upper_count = 0

        for counter in self.__gen_statistic():
            total_count += 1

            if not counter[CounterKey.TOTAL]:
                continue

            fail_ratio = counter[CounterKey.FAIL] / counter[CounterKey.TOTAL]

            if fail_ratio >= self._error_ratio:
                upper_count += 1

        if not total_count:
            return 0

        return upper_count / total_count

    def _compute_state(self):
        current_time = self._get_time()

        if current_time < self._stuck_until:
            # Skip state changing until
            return

        if self._state is CircuitBreakerStates.BROKEN:
            self._state = CircuitBreakerStates.RECOVERING
            self._recovery_at = current_time
            return

        # Do not compute when not enough statistic
        if (
            self._state is CircuitBreakerStates.PASSING
            and len(self._statistic) < self.BUCKET_COUNT
        ):
            return

        recovery_ratio = self.recovery_ratio

        if self._state is CircuitBreakerStates.PASSING:
            if recovery_ratio >= self.PASSING_BROKEN_THRESHOLD:
                self._stuck_until = current_time + self._broken_time
                self._state = CircuitBreakerStates.BROKEN
                self._statistic.clear()
            return

        if self._state is not CircuitBreakerStates.RECOVERING:
            return

        if recovery_ratio >= (
            self.RECOVER_BROKEN_THRESHOLD * self._error_ratio
        ):
            self._stuck_until = current_time + self._broken_time
            self._state = CircuitBreakerStates.BROKEN
            self._statistic.clear()
            return

        recovery_length = current_time - self._recovery_at
        if recovery_length >= self._recovery_time:
            self._stuck_until = current_time + self._passing_time
            self._state = CircuitBreakerStates.PASSING
            return

    @contextmanager
    def context(self):
        counter = self.counter()
        self._compute_state()

        if self._state is CircuitBreakerStates.PASSING:
            yield from self._on_passing(counter)
            return

        elif self._state is CircuitBreakerStates.BROKEN:
            return (yield from self._on_broken())

        elif self._state is CircuitBreakerStates.RECOVERING:
            yield from self._on_recover(counter)
            return

        raise NotImplementedError(self._state)

    def call(self, func, *args, **kwargs):
        with self.context():
            return func(*args, **kwargs)

    async def call_async(self, func, *args, **kwargs):
        with self.context():
            return await awaitable(func)(*args, **kwargs)

    def __repr__(self):
        return "<{}: state={!r} recovery_ratio={!s}>".format(
            self.__class__.__name__, self._state, self.recovery_ratio,
        )


def cutout(ratio: float, response_time: typing.Union[int, float],
           *exceptions: typing.Type[Exception], **kwargs):

    circuit_breaker = CircuitBreaker(
        error_ratio=ratio,
        response_time=response_time,
        exceptions=exceptions,
        **kwargs
    )

    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kw):
            return await circuit_breaker.call_async(func, *args, **kw)

        @wraps(func)
        def wrapper(*args, **kw):
            return circuit_breaker.call(func, *args, **kw)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper

        return wrapper

    return decorator
