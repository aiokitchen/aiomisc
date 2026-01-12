import asyncio
from unittest.mock import patch

import pytest

from aiomisc.cron import CronCallback

# Fixed delay for deterministic testing
TICK_DELAY = 0.1


def mock_get_next(*args):
    """Return a fixed delay for deterministic testing."""
    return TICK_DELAY


@patch.object(CronCallback, "get_next", mock_get_next)
async def test_cron(event_loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop)

    # Wait for at least 2 ticks
    await asyncio.sleep(TICK_DELAY * 2.5)
    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 2

    await asyncio.sleep(TICK_DELAY * 2)

    # Counter should not increase after stop
    assert counter == 2


@patch.object(CronCallback, "get_next", mock_get_next)
async def test_long_func(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            await asyncio.sleep(TICK_DELAY * 2)  # Longer than tick interval
            counter += 1
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 1


@patch.object(CronCallback, "get_next", mock_get_next)
async def test_shield(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition
        counter += 1
        async with condition:
            condition.notify_all()
        await asyncio.sleep(TICK_DELAY * 2)
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop, shield=True)

    # Wait for cron callback to start
    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    await asyncio.sleep(TICK_DELAY * 3)

    # Shielded - task should complete
    assert counter == 2


@patch.object(CronCallback, "get_next", mock_get_next)
async def test_restart(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition
        counter += 1
        async with condition:
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 2)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 2

    await asyncio.sleep(TICK_DELAY * 2)

    # Counter should not increase after stop
    assert counter == 2

    cron.start("* * * * * *", event_loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 4)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 4

    await asyncio.sleep(TICK_DELAY * 2)

    # Counter should not increase after stop
    assert counter == 4
