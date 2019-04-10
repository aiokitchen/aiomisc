import asyncio
import pytest

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_periodic(loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop)

    await asyncio.sleep(0.5, loop=loop)
    periodic.stop()

    assert 4 < counter < 7

    await asyncio.sleep(0.5, loop=loop)

    assert 4 < counter < 7


async def test_long_func(loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(0.5)

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop)

    await asyncio.sleep(1, loop=loop)
    periodic.stop()

    assert 1 < counter < 3


async def test_shield(loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(2)

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop, shield=True)

    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    assert counter == 1

    # No shield
    counter = 0
    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop, shield=False)

    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    assert counter == 0
