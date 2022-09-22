import asyncio
import logging
import threading
from collections import Counter, deque
from contextlib import contextmanager
from enum import IntEnum, unique
from functools import wraps
from random import random
from typing import Any, Awaitable, Callable
from typing import Counter as CounterType
from typing import (
    Deque, Generator, Iterable, Optional, Tuple, Type, TypeVar, Union,
)

from aiomisc.compat import EventLoopMixin
from aiomisc.counters import Statistic
from aiomisc.utils import awaitable


log = logging.getLogger(__name__)
Number = Union[int, float]
StatisticType = Deque[Tuple[int, Counter]]
T = TypeVar("T")
ExceptionInspectorType = Optional[Callable[[Exception], bool]]


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


class CircuitBreakerStatistic(Statistic):
    call_count: int
    error_ratio: float
    error_ratio_threshold: float
    call_passing: int
    call_broken: int
    call_recovering: int
    call_recovering_ok: int
    call_recovering_failed: int


class CircuitBroken(Exception):
    __slots__ = ("last_exception",)

    def __init__(self, last_exception: Optional[Exception]):
        self.last_exception = last_exception

    def __repr__(self) -> str:
        return "<{!r}: {!r}>".format(self, self.last_exception)


class CircuitBreaker(EventLoopMixin):
    __slots__ = (
        "_broken_time",
        "_counters",
        "_error_ratio",
        "_exceptions",
        "_exception_inspector",
        "_last_exception",
        "_lock",
        "_passing_time",
        "_recovery_at",
        "_recovery_ratio",
        "_recovery_time",
        "_response_time",
        "_state",
        "_statistic",
        "_stuck_until",
    ) + EventLoopMixin.__slots__

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

    _stuck_until: Number
    _recovery_at: Number
    _last_exception: Optional[Exception]

    def __init__(
        self,
        error_ratio: float,
        response_time: Number,
        exceptions: Iterable[Type[Exception]] = (Exception,),
        recovery_time: Number = None,
        broken_time: Number = None,
        passing_time: Number = None,
        exception_inspector: ExceptionInspectorType = None,
        statistic_name: Optional[str] = None,
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
                "Error ratio must be between 0 and 1 not %r" % error_ratio,
            )

        self._statistic: StatisticType = deque(
            maxlen=self.BUCKET_COUNT,
        )
        self._lock = threading.RLock()
        self._error_ratio = error_ratio
        self._state = CircuitBreakerStates.PASSING
        self._response_time = response_time
        self._stuck_until = 0
        self._recovery_at = 0

        self._exceptions = tuple(frozenset(exceptions))
        self._exception_inspector = exception_inspector

        self._passing_time = passing_time or self._response_time
        self._broken_time = broken_time or self._response_time
        self._recovery_time = recovery_time or self._response_time
        self._last_exception = None
        self._counters = CircuitBreakerStatistic(statistic_name)
        self._counters.error_ratio_threshold = error_ratio

    @property
    def response_time(self) -> Number:
        return self._response_time

    @property
    def state(self) -> CircuitBreakerStates:
        return self._state

    def _get_time(self) -> float:
        return self.loop.time()

    def bucket(self) -> int:
        ts = self._get_time() * self.BUCKET_COUNT
        return int(ts - (ts % self._response_time))

    def counter(self) -> Counter:
        with self._lock:
            current = self.bucket()

            if not self._statistic:
                # Empty statistic just return a new counter
                counter: CounterType[int] = Counter()
                self._statistic.append((current, counter))
                return counter

            bucket, counter = self._statistic[-1]

            if current != bucket:
                # Append Counter to statistic or shift when maxsize reached
                counter = Counter()
                self._statistic.append((current, counter))

            return counter

    def __gen_statistic(self) -> Generator[Counter, None, None]:
        """
        Generator which returns only buckets Counters not before current_time
        """
        not_before = self.bucket() - (self._response_time * self.BUCKET_COUNT)

        for idx in range(len(self._statistic) - 1, -1, -1):
            bucket, counter = self._statistic[idx]

            if bucket < not_before:
                break

            yield counter

    def get_state_delay(self) -> Number:
        delay = self._stuck_until - self._get_time()
        return max(delay, 0)

    def _inspect_exception(self, e: Exception) -> int:
        if not self._exception_inspector:
            return 1

        # noinspection PyBroadException
        try:
            return 1 if self._exception_inspector(e) else 0
        except Exception:
            log.exception(
                "Unhandled exception in %r",
                self._exception_inspector,
            )
            return 1

    def _on_passing(
        self, counter: CounterType[int],
    ) -> Generator[Any, Any, Any]:
        try:
            yield
            counter[CounterKey.OK] += 1
            self._last_exception = None
        except self._exceptions as e:
            self._last_exception = e
            counter[CounterKey.FAIL] += self._inspect_exception(e)
            raise
        finally:
            counter[CounterKey.TOTAL] += 1

    def _on_recover(
        self, counter: CounterType[int],
    ) -> Generator[Any, Any, Any]:
        current_time = self._get_time()
        condition = (random() + 1) < (
            2 ** ((current_time - self._recovery_at) / self._recovery_time)
        )

        if not condition:
            self._counters.call_recovering_failed += 1
            raise CircuitBroken(self._last_exception)

        self._counters.call_recovering_ok += 1
        yield from self._on_passing(counter)

    @property
    def recovery_ratio(self) -> Number:
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

    def _compute_state(self) -> None:
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
    def context(self) -> Generator[Any, Any, Any]:
        counter = self.counter()
        self._compute_state()
        self._counters.call_count += 1

        if self._state is CircuitBreakerStates.PASSING:
            self._counters.call_passing += 1
            yield from self._on_passing(counter)
            return

        elif self._state is CircuitBreakerStates.BROKEN:
            self._counters.call_broken += 1
            raise CircuitBroken(self._last_exception)

        elif self._state is CircuitBreakerStates.RECOVERING:
            self._counters.call_recovering += 1
            yield from self._on_recover(counter)
            return

        raise NotImplementedError(self._state)

    def call(
        self, func: Callable[..., T], *args: Any, **kwargs: Any
    ) -> T:
        with self.context():
            return func(*args, **kwargs)

    async def call_async(
        self, func: Callable[..., Awaitable[T]],
        *args: Any, **kwargs: Any
    ) -> T:
        with self.context():
            return await awaitable(func)(*args, **kwargs)   # type: ignore

    def __repr__(self) -> str:
        return "<{}: state={!r} recovery_ratio={!s}>".format(
            self.__class__.__name__, self._state, self.recovery_ratio,
        )


CutoutFuncType = Union[Callable[..., T], Callable[..., Awaitable[T]]]
CutoutDecoratorReturnType = Callable[..., Union[T, Awaitable[T]]]
CutoutReturnType = Callable[[CutoutFuncType], CutoutDecoratorReturnType]


def cutout(
    ratio: float, response_time: Union[int, float],
    *exceptions: Type[Exception], **kwargs: Any
) -> CutoutReturnType:
    circuit_breaker = CircuitBreaker(
        error_ratio=ratio,
        response_time=response_time,
        exceptions=exceptions,
        **kwargs
    )

    def decorator(func: CutoutFuncType) -> CutoutDecoratorReturnType:
        @wraps(func)
        async def async_wrapper(
            *args: Any, **kw: Any
        ) -> T:
            return await circuit_breaker.call_async(func, *args, **kw)

        @wraps(func)
        def wrapper(*args: Any, **kw: Any) -> T:
            return circuit_breaker.call(func, *args, **kw)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper

        return wrapper

    return decorator
