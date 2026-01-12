import asyncio
from unittest.mock import patch

import pytest

import aiomisc
from aiomisc.cron import CronCallback
from aiomisc.service.cron import CronService

pytestmark = pytest.mark.catch_loop_exceptions


# Fixed delay for deterministic testing
TICK_DELAY = 0.1


def mock_get_next(*args):
    """Return a fixed delay for deterministic testing."""
    return TICK_DELAY


@patch.object(CronCallback, "get_next", mock_get_next)
def test_cron():
    counter = 0
    condition: asyncio.Condition

    async def callback():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    svc = CronService()

    svc.register(callback, spec="* * * * * *")

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == 1), timeout=2
            )

        await svc.stop()

        await asyncio.sleep(TICK_DELAY * 2)
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == 1), timeout=2
            )

        assert counter == 1

    with aiomisc.entrypoint(svc) as loop:
        condition = asyncio.Condition()

        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))


@patch.object(CronCallback, "get_next", mock_get_next)
def test_register():
    counter = 0
    condition: asyncio.Condition

    async def callback():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    svc = CronService()

    svc.register(callback, spec="* * * * * *")
    svc.register(callback, spec="* * * * * */2")  # even second
    svc.register(callback, spec="* * * * * *")

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        # With mocked timing, all 3 callbacks fire every TICK_DELAY
        # After ~2 ticks we expect 6 calls (3 callbacks * 2 ticks)
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter >= 5), timeout=10
            )

        await svc.stop()

        final_counter = counter
        await asyncio.sleep(TICK_DELAY * 2)
        # Counter should not increase after stop
        assert counter == final_counter

    with aiomisc.entrypoint(svc) as loop:
        condition = asyncio.Condition()
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))
