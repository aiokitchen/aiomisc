import asyncio

import pytest

from aiomisc.cron import CronCallback


@pytest.mark.flaky(max_runs=5, min_passes=3)
async def test_cron(event_loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop)

    await asyncio.sleep(2)
    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 2

    await asyncio.sleep(2)

    assert counter == 2


@pytest.mark.flaky(max_runs=5, min_passes=3)
async def test_long_func(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            await asyncio.sleep(1)
            counter += 1
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 1


@pytest.mark.flaky(max_runs=5, min_passes=3)
async def test_shield(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition  # noqa
        counter += 1
        async with condition:
            condition.notify_all()
        await asyncio.sleep(1)
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", event_loop, shield=True)

    # Wait for cron callback to start
    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    await asyncio.sleep(1.5)

    # Shielded
    assert counter == 2


@pytest.mark.flaky(max_runs=5, min_passes=3)
async def test_restart(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition  # noqa
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

    await asyncio.sleep(2)

    assert counter == 2

    cron.start("* * * * * *", event_loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 4)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 4

    await asyncio.sleep(2)

    assert counter == 4
