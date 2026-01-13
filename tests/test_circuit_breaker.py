import asyncio
from collections import Counter
from typing import Type, Union
from collections.abc import MutableMapping

import pytest

import aiomisc
from aiomisc.circuit_breaker import (
    CircuitBreakerStates as States,
    CircuitBroken,
)

pytestmark = pytest.mark.catch_loop_exceptions


class CallContainer:
    def __init__(self):
        self.failed = False

    def __call__(self, *args, **kwargs):
        if self.failed:
            raise RuntimeError

        return


class PatchedCircuitBreaker(aiomisc.CircuitBreaker):
    """
    CircuitBreaker for young time travelers
    """

    _TIME = 0.0

    @classmethod
    def tick(cls, second=1.0):
        cls._TIME += second

    @classmethod
    def reset(cls):
        cls._TIME += 1000000000.0

    def _get_time(self):
        return float(self._TIME)


async def test_simple(event_loop):
    PatchedCircuitBreaker.reset()
    circuit_breaker = PatchedCircuitBreaker(error_ratio=0.5, response_time=10)

    ctx = CallContainer()

    # Zero ratio on start
    assert circuit_breaker.recovery_ratio == 0

    # PASSING state
    for _ in range(10):
        PatchedCircuitBreaker.tick()
        circuit_breaker.call(ctx)

    assert circuit_breaker.recovery_ratio == 0
    assert circuit_breaker.state == States.PASSING

    # Now context return exceptions
    ctx.failed = True

    # Errored calls
    for _ in range(10):
        PatchedCircuitBreaker.tick()

        with pytest.raises(RuntimeError):
            circuit_breaker.call(ctx)

    # Change state to BROKEN
    with pytest.raises(CircuitBroken):
        circuit_breaker.call(ctx)

    assert circuit_breaker.state == States.BROKEN

    # Delaying in BROKEN state
    assert circuit_breaker.get_state_delay() > 0

    # Waiting in BROKEN state
    for _ in range(10):
        PatchedCircuitBreaker.tick()

        with pytest.raises(CircuitBroken):
            circuit_breaker.call(ctx)

    responses: MutableMapping[bool | type[Exception], int] = Counter()

    # Delay is zero
    assert circuit_breaker.get_state_delay() == 0

    # Collect statistic in RECOVERY state
    for _ in range(110):
        PatchedCircuitBreaker.tick(0.1)

        try:
            circuit_breaker.call(ctx)
        except CircuitBroken:
            responses[CircuitBroken] += 1
        except RuntimeError:
            responses[RuntimeError] += 1

    assert responses[CircuitBroken]
    assert responses[RuntimeError]

    # Waiting to switch from BROKEN to RECOVERY
    PatchedCircuitBreaker.tick(circuit_breaker.get_state_delay())

    ctx.failed = False

    responses.clear()

    # RECOVERY to PASSING state
    for _ in range(10):
        PatchedCircuitBreaker.tick()

        try:
            circuit_breaker.call(ctx)
            responses[True] += 1
        except CircuitBroken:
            responses[CircuitBroken] += 1
        except RuntimeError:
            responses[RuntimeError] += 1

    assert not responses.get(RuntimeError)
    assert responses[CircuitBroken]
    assert responses[True]

    responses.clear()
    ctx.failed = False

    # PASSING state
    for _ in range(20):
        PatchedCircuitBreaker.tick()

        try:
            circuit_breaker.call(ctx)
            responses[True] += 1
        except CircuitBroken:
            responses[CircuitBroken] += 1
        except RuntimeError:
            responses[RuntimeError] += 1

    assert not responses.get(CircuitBroken)
    assert responses[True]


async def test_get_time():
    cb = aiomisc.CircuitBreaker(0.5, 1)
    assert cb._get_time()
    time = cb._get_time()
    await asyncio.sleep(0.02)
    assert cb._get_time() > time


async def test_bad_response_time():
    with pytest.raises(ValueError):
        aiomisc.CircuitBreaker(0.5, 0)


def test_exception_inspector():
    def inspector(exc: Exception) -> bool:
        if isinstance(exc, ValueError):
            return False
        return True

    cb = PatchedCircuitBreaker(
        error_ratio=0.5, response_time=5, exception_inspector=inspector
    )

    PatchedCircuitBreaker.reset()

    def raiser(exc_type):
        raise exc_type()

    for i in range(100):
        PatchedCircuitBreaker.tick(0.1)
        with pytest.raises(ValueError):
            cb.call(raiser, ValueError)

        assert cb.recovery_ratio == 0

    PatchedCircuitBreaker.tick(1)

    for i in range(10):
        PatchedCircuitBreaker.tick(0.1)
        with pytest.raises(RuntimeError):
            cb.call(raiser, RuntimeError)

        assert cb.recovery_ratio > 0
