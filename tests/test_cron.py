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
    cron.stop()

    assert counter == 2

    await asyncio.sleep(2)

    assert counter == 2


async def test_long_func(loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(1)

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(1.5)
    cron.stop()

    assert counter == 1


async def test_shield(loop):
    counter = 0

    async def task():
        nonlocal counter
        await asyncio.sleep(1)
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", loop, shield=True)

    # Wait for cron callback to start
    while cron.task is None:
        await asyncio.sleep(0.1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    # Wait for counter to increment
    await asyncio.sleep(1)

    # Shielded
    assert counter == 1

    # No shield
    counter = 0
    cron = CronCallback(task)
    cron.start("* * * * * *", loop, shield=False)

    # Wait for cron callback to start
    while cron.task is None:
        await asyncio.sleep(0.1)

    with pytest.raises(asyncio.CancelledError):
        await cron.stop()

    # Wait for counter to increment
    await asyncio.sleep(1)

    # Cancelled
    assert counter == 0


async def test_restart(loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    cron.stop()

    assert counter == 2

    await asyncio.sleep(2)

    assert counter == 2

    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    cron.stop()

    assert counter == 4

    await asyncio.sleep(2)

    assert counter == 4
