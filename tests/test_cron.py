import asyncio
import pytest
from aiomisc.cron import CronCallback


async def test_cron(loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 2

    await asyncio.sleep(2)

    assert counter == 2


async def test_long_func(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            await asyncio.sleep(1)
            counter += 1
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 1


async def test_shield(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition
        counter += 1
        async with condition:
            condition.notify_all()
        await asyncio.sleep(1)
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", loop, shield=True)

    # Wait for cron callback to start
    async with condition:
        await condition.wait_for(lambda: counter >= 1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    await asyncio.sleep(1.5)

    # Shielded
    assert counter == 2


async def test_restart(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter, condition
        counter += 1
        async with condition:
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 2)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 2

    await asyncio.sleep(2)

    assert counter == 2

    cron.start("* * * * * *", loop)

    async with condition:
        await condition.wait_for(lambda: counter >= 4)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    assert counter == 4

    await asyncio.sleep(2)

    assert counter == 4
