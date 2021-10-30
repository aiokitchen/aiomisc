import asyncio
from datetime import timedelta

import pytest
from freezegun import freeze_time

from aiomisc.cron import CronCallback


async def test_cron(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            counter += 1
            await asyncio.sleep(0)
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    async with condition:
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
            counter += 1
            await asyncio.sleep(1.1)
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(1)
    async with condition:
        await cron.stop()
    await asyncio.sleep(2)

    assert counter == 1


async def test_shield(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            await asyncio.sleep(1.1)
            counter += 1
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop, shield=True)

    # Wait for cron callback to start
    while cron.task is None:
        await asyncio.sleep(0.1)

    async with condition:
        with pytest.raises(asyncio.CancelledError):
            await cron.stop()

    # Wait for counter to increment
    await asyncio.sleep(1.1)

    # Shielded
    assert counter == 1

    # No shield
    counter = 0
    cron = CronCallback(task)
    cron.start("* * * * * *", loop, shield=False)

    # Wait for cron callback to start
    while cron.task is None:
        await asyncio.sleep(0.1)

    async with condition:
        with pytest.raises(asyncio.CancelledError):
            await cron.stop()

    # Wait for counter to increment
    await asyncio.sleep(1)

    # Cancelled
    assert counter == 0


async def test_restart(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    cron = CronCallback(task)
    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    async with condition:
        await cron.stop()
    await asyncio.sleep(2)

    assert counter == 2

    cron.start("* * * * * *", loop)

    await asyncio.sleep(2)
    async with condition:
        await cron.stop()
    await asyncio.sleep(2)

    assert counter == 4


@pytest.mark.parametrize(
    "now",
    [
        "2021-02-14T07:30:00.532766+00:00",
        "2021-02-14T07:00:00.532766+01:00",
        "2021-02-14T07:00:00.532766+02:00",
        "2021-02-14T07:00:00.532766+03:00",
        "2021-02-14T07:00:00.532766+04:00",
    ],
)
async def test_tz_next(loop, now):
    cron = CronCallback(lambda: True)
    with freeze_time(now):
        cron.start("*/10 * * * *", loop)
        expected = timedelta(minutes=10).total_seconds()
        assert 0 <= cron.get_current() - loop.time() <= expected
