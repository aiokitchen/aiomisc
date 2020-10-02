import asyncio
from collections import Counter

import pytest

import aiomisc
from aiomisc.circuit_breaker import CircuitBreakerStates as States
from aiomisc.circuit_breaker import CircuitBroken


pytestmark = pytest.mark.catch_loop_exceptions


class CallContainer:
    def __init__(self):
        self.failed = False

    def __call__(self, *args, **kwargs):
        if self.failed:
            raise RuntimeError

        return


class PatchedCircuitBreaper(aiomisc.CircuitBreaker):
    _TIME = 0

    @classmethod
    def tick(cls, second=1.0):
        cls._TIME += second

    @classmethod
    def reset(cls):
        cls._TIME += 1000000000.0

    def _get_time(self):
        return float(self._TIME)


async def test_simple(loop):

    PatchedCircuitBreaper.reset()
    circuit_breaker = PatchedCircuitBreaper(
        error_ratio=0.5, response_time=10,
    )

    ctx = CallContainer()
    responses = Counter()

    assert circuit_breaker.recovery_ratio == 0

    await asyncio.sleep(0)

    for _ in range(10):
        PatchedCircuitBreaper.tick()
        circuit_breaker.call(ctx)

    assert circuit_breaker.recovery_ratio == 0
    assert circuit_breaker.state == States.PASSING

    ctx.failed = True

    for _ in range(10):
        PatchedCircuitBreaper.tick()

        with pytest.raises(RuntimeError):
            circuit_breaker.call(ctx)

    with pytest.raises(CircuitBroken):
        circuit_breaker.call(ctx)

    assert circuit_breaker.state == States.BROKEN

    for _ in range(10):
        PatchedCircuitBreaper.tick()

        with pytest.raises(CircuitBroken):
            circuit_breaker.call(ctx)

    responses.clear()

    for _ in range(110):
        PatchedCircuitBreaper.tick(0.1)

        try:
            circuit_breaker.call(ctx)
        except CircuitBroken:
            responses[CircuitBroken] += 1
        except RuntimeError:
            responses[RuntimeError] += 1

    assert responses[CircuitBroken]
    assert responses[RuntimeError]

    ctx.failed = False

    responses.clear()

    for _ in range(20):
        PatchedCircuitBreaper.tick()

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

    for _ in range(10):
        PatchedCircuitBreaper.tick()

        try:
            circuit_breaker.call(ctx)
            responses[True] += 1
        except CircuitBroken:
            responses[CircuitBroken] += 1
        except RuntimeError:
            responses[RuntimeError] += 1

    assert not responses.get(CircuitBroken)
    assert responses[True]
