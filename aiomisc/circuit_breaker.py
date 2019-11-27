import asyncio
import threading
import time
import typing
from collections import deque, Counter
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
        "_passing_time",
        "_recovery_time",
        "_recovery_ratio",
        "_response_time",
        "_state",
        "_statistic",
        "_stuck_until",
        "_recovery_at",
    )

    BUCKET_COUNT = 10

    # Ratio of
    RECOVER_BROKEN_THRESHOLD = 0.2
    PASSING_BROKEN_THRESHOLD = 1

    def __init__(
        self,
        error_ratio: float,
        response_time: TimeType,
        *exceptions: typing.Type[Exception],
        recovery_time: TimeType = None,
        broken_time: TimeType = None,
        passing_time: TimeType = None
    ):

        self._statistic = deque(maxlen=self.BUCKET_COUNT)  # type: StatisticType
        self._lock = threading.RLock()
        self._error_ratio = error_ratio
        self._state = CircuitBreakerStates.PASSING
        self._response_time = response_time
        self._stuck_until = 0
        self._recovery_at = 0

        self._exceptions = tuple(frozenset(exceptions)) or (Exception,)

        self._passing_time = passing_time or self._response_time
        self._broken_time = broken_time or self._response_time
        self._recovery_time = recovery_time or self._response_time

    @property
    def response_time(self) -> TimeType:
        return self._response_time

    @property
    def state(self) -> CircuitBreakerStates:
        return self._state

    def bucket(self) -> int:
        ts = time.monotonic() * self.BUCKET_COUNT
        return int(ts - (ts % self._response_time))

    def counter(self) -> Counter:
        with self._lock:
            current = self.bucket()

            if not len(self._statistic):
                counter = Counter()
                self._statistic.append((current, counter))
                return counter

            bucket, counter = self._statistic[-1]

            if current != bucket:
                counter = Counter()
                self._statistic.append((current, counter))

            return counter

    def __gen_statistic(self) -> typing.Generator[Counter, None, None]:
        not_before = self.bucket() - (self._response_time * self.BUCKET_COUNT)

        for idx in range(len(self._statistic) - 1, -1, -1):
            bucket, counter = self._statistic[idx]

            if bucket < not_before:
                break

            yield counter

    def get_state_delay(self):
        delay = self._stuck_until - time.monotonic()
        if delay < 0:
            return 0
        return delay

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
        current_time = time.monotonic()
        condition = (random() + 1) < (
            2 ** ((current_time - self._recovery_at) / self._recovery_time)
        )

        if condition:
            yield from self._on_passing(counter)
        else:
            raise CircuitBroken()

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

        return upper_count / total_count

    def _compute_state(self):
        current_time = time.monotonic()

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

        if self._state is CircuitBreakerStates.RECOVERING:
            if recovery_ratio >= self.RECOVER_BROKEN_THRESHOLD:
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
    def _exec(self):
        counter = self.counter()
        self._compute_state()

        if self._state is CircuitBreakerStates.PASSING:
            yield from self._on_passing(counter)
            return

        elif self._state is CircuitBreakerStates.BROKEN:
            yield from self._on_broken()
            return

        elif self._state is CircuitBreakerStates.RECOVERING:
            yield from self._on_recover(counter)
            return

        raise NotImplementedError(self._state)

    def call(self, func, *args, **kwargs):
        with self._exec():
            return func(*args, **kwargs)

    async def call_async(self, func, *args, **kwargs):
        with self._exec():
            return await awaitable(func)(*args, **kwargs)

    def __repr__(self):
        return "<{}: state={!r} recovery_ratio={!s}>".format(
            self.__class__.__name__, self._state, self.recovery_ratio
        )


def cutoff(ratio, recovery_time, *exceptions):
    circuit_breaker = CircuitBreaker(
        error_ratio=ratio, recovery_time=recovery_time, *exceptions
    )

    async def decorator(func):
        @wraps(func)
        async def async_wrap(*args, **kwargs):
            return await circuit_breaker.call_async(func, *args, **kwargs)

        @wraps(func)
        def wrap(*args, **kwargs):
            return circuit_breaker.call(func, *args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrap
        else:
            return wrap

    return decorator
