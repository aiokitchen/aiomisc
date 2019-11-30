import asyncio
import time
from contextlib import suppress

import pytest
import aiomisc
from aiomisc.circuit_breaker import CircuitBreakerStates as States, \
    CircuitBroken

pytestmark = pytest.mark.catch_loop_exceptions


class CallContainer:
    def __init__(self):
        self.failed = False

    def __call__(self, *args, **kwargs):
        if self.failed:
            raise RuntimeError

        return


async def test_simple(loop):
    circuit_breaker = aiomisc.CircuitBreaker(
        error_ratio=0.5, response_time=0.5
    )

    ctx = CallContainer()

    assert circuit_breaker.recovery_ratio == 0

    for _ in range(10):
        await asyncio.sleep(0.05)
        circuit_breaker.call(ctx)

    assert circuit_breaker.recovery_ratio == 0
    assert circuit_breaker.state == States.PASSING

    ctx.failed = True

    for _ in range(10):
        await asyncio.sleep(0.05)

        with pytest.raises(RuntimeError):
            circuit_breaker.call(ctx)

    for _ in range(10):
        try:
            circuit_breaker.call(ctx)
        except (RuntimeError, CircuitBroken):
            pass

    assert circuit_breaker.state == States.BROKEN

    # assert circuit_breaker.state == 0, circuit_breaker
    #
    # for _ in range(10):
    #     with suppress(ZeroDivisionError):
    #         circuit_breaker.call(lambda a, b: a / b, 1, 0)
    #
    # with suppress(aiomisc.CircuitBroken):
    #     circuit_breaker.call(lambda a, b: a / b, 1, 0)
    #
    # assert circuit_breaker.state != 0, circuit_breaker
    #
    # with pytest.raises(aiomisc.CircuitBroken):
    #     circuit_breaker.call(lambda a, b: a / b, 1, 0)
    #
    # time.sleep(circuit_breaker.response_time / 10)
    #
    # def run(num=1000, delay=0.001):
    #     ok = 0
    #     broken = 0
    #
    #     for _ in range(num):
    #         time.sleep(delay)
    #
    #         try:
    #             circuit_breaker.call(lambda a, b: a / b, 1, 1)
    #         except aiomisc.CircuitBroken:
    #             broken += 1
    #         else:
    #             ok += 1
    #
    #     return ok, broken
    #
    # ok, broken = run(500, 0.001)
    # assert ok == 0
    #
    # time.sleep(circuit_breaker.response_time / 6)
    #
    # ok, broken = run()
    # assert ok == pytest.approx(broken), circuit_breaker._state
    #
    # time.sleep(circuit_breaker.response_time)
    #
    # with pytest.raises(ZeroDivisionError):
    #     circuit_breaker.call(lambda a, b: a / b, 1, 0)
