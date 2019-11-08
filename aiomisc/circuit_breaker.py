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


RecoveryTimeType = typing.Union[int, float]


@unique
class CounterKey(IntEnum):
    FAIL = 0
    OK = 1
    TOTAL = 2


@unique
class CircuitBreakerStates(IntEnum):
    PASSING = 0
    BROKEN = 1
    RECOVER = 2


class CircuitBroken(Exception):
    pass


class CircuitBreaker:
    __slots__ = (
        'ratio', 'lock', 'recovery_time', 'statistic', 'exceptions', 'state',
        'recovery_ratio'
    )

    BUCKET_COUNT = 10

    RECOVER_THRESHOLD = 0
    PASSING_THRESHOLD = 0.5
    BROKEN_THRESHOLD = 1.0

    def __init__(self, ratio: float,
                 recovery_time: RecoveryTimeType,
                 *exceptions: typing.Type[Exception]):

        self.lock = threading.RLock()
        self.ratio = ratio
        self.state = CircuitBreakerStates.PASSING
        self.recovery_time = recovery_time
        self.recovery_ratio = 0
        self.statistic = deque(
            maxlen=self.BUCKET_COUNT
        )  # type: typing.Deque[typing.Tuple[int, Counter]]
        self.exceptions = tuple(frozenset(exceptions)) or (Exception,)

    def bucket(self) -> int:
        ts = time.monotonic() * self.BUCKET_COUNT
        return int(ts - (ts % self.recovery_time))

    def counter(self) -> Counter:
        with self.lock:
            current = self.bucket()

            if not len(self.statistic):
                counter = Counter()
                self.statistic.append((current, counter))
                return counter

            bucket, counter = self.statistic[-1]

            if current != bucket:
                counter = Counter()
                self.statistic.append((current, counter))

            return counter

    def __iter__(self) -> typing.Generator[Counter, None, None]:
        not_before = (
            self.bucket() - (self.recovery_time * self.BUCKET_COUNT)
        )

        for idx in range(len(self.statistic) - 1, -1, -1):
            bucket, counter = self.statistic[idx]

            if bucket < not_before:
                break

            yield counter

    def delay(self):
        return (self.bucket() + self.recovery_time) - time.monotonic()

    def _on_passing(self, counter):
        try:
            yield
            counter[CounterKey.OK] += 1
        except self.exceptions:
            counter[CounterKey.FAIL] += 1
            raise
        finally:
            counter[CounterKey.TOTAL] += 1

    def _on_broken(self):
        raise CircuitBroken()

    def _on_recover(self, counter):
        if random() > self.recovery_ratio:
            yield from self._on_passing(counter)
        else:
            raise CircuitBroken()

    def _compute_state(self):
        upper_count = 0
        total_count = 0

        for idx, counter in enumerate(self):
            total_count += 1

            if not counter[CounterKey.TOTAL]:
                continue

            fail_ratio = counter[CounterKey.FAIL] / counter[CounterKey.TOTAL]

            if fail_ratio >= self.ratio:
                upper_count += 1

        self.recovery_ratio = upper_count / total_count

        if self.state is CircuitBreakerStates.PASSING:
            if self.recovery_ratio >= self.BROKEN_THRESHOLD:
                self.state = CircuitBreakerStates.BROKEN
            return

        elif self.state is CircuitBreakerStates.RECOVER:
            if self.recovery_ratio < self.PASSING_THRESHOLD:
                self.state = CircuitBreakerStates.PASSING
            return

        elif self.state is CircuitBreakerStates.BROKEN:
            if self.recovery_ratio <= self.RECOVER_THRESHOLD:
                self.state = CircuitBreakerStates.RECOVER
            return

    @contextmanager
    def _exec(self):
        counter = self.counter()
        self._compute_state()

        if self.state is CircuitBreakerStates.PASSING:
            yield from self._on_passing(counter)
            return

        elif self.state is CircuitBreakerStates.BROKEN:
            yield from self._on_broken()
            return

        elif self.state is CircuitBreakerStates.RECOVER:
            yield from self._on_recover(counter)
            return

        raise NotImplementedError(self.state)

    def call(self, func, *args, **kwargs):
        with self._exec():
            return func(*args, **kwargs)

    async def call_async(self, func, *args, **kwargs):
        with self._exec():
            return await awaitable(func)(*args, **kwargs)

    def __repr__(self):
        return "<{}: state={!r} recovery_ratio={!s}>".format(
            self.__class__.__name__,
            self.state, self.recovery_ratio,
        )


def cutoff(ratio, recovery_time, *exceptions):
    circuit_breaker = CircuitBreaker(
        ratio=ratio,
        recovery_time=recovery_time,
        *exceptions
    )

    async def decorator(func):
        @wraps(func)
        def async_wrap(*args, **kwargs):
            return await circuit_breaker.call_async(func, *args, **kwargs)

        @wraps(func)
        def wrap(*args, **kwargs):
            return circuit_breaker.call(func, *args, **kwargs)

        if asyncio.iscoroutinefunction(func):
            return async_wrap
        else:
            return wrap

    return decorator
