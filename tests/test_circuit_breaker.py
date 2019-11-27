import time
from contextlib import suppress

import pytest
import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_simple(loop):
    circuit_breaker = aiomisc.CircuitBreaker(error_ratio=0.5, recovery_time=1)

    for _ in range(10):
        circuit_breaker.call(lambda: None)

    assert circuit_breaker._state == 0, circuit_breaker

    for _ in range(10):
        with suppress(ZeroDivisionError):
            circuit_breaker.call(lambda a, b: a / b, 1, 0)

    with suppress(aiomisc.CircuitBroken):
        circuit_breaker.call(lambda a, b: a / b, 1, 0)

    assert circuit_breaker._state != 0, circuit_breaker

    with pytest.raises(aiomisc.CircuitBroken):
        circuit_breaker.call(lambda a, b: a / b, 1, 0)

    time.sleep(circuit_breaker._reaction_time / 10)

    def run(num=1000, delay=0.001):
        ok = 0
        broken = 0

        for _ in range(num):
            time.sleep(delay)

            try:
                circuit_breaker.call(lambda a, b: a / b, 1, 1)
            except aiomisc.CircuitBroken:
                broken += 1
            else:
                ok += 1

        return ok, broken

    ok, broken = run(500, 0.001)
    assert ok == 0

    time.sleep(circuit_breaker._reaction_time / 6)

    ok, broken = run()
    assert ok == pytest.approx(broken), circuit_breaker._state

    time.sleep(circuit_breaker._reaction_time)

    with pytest.raises(ZeroDivisionError):
        circuit_breaker.call(lambda a, b: a / b, 1, 0)
