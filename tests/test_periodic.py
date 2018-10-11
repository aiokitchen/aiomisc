import asyncio
import pytest

from aiomisc.periodic import PeriodicCallback


@pytest.mark.asyncio
async def test_periodic(event_loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    periodic = PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    await asyncio.sleep(0.5, loop=event_loop)
    periodic.stop()

    assert 4 < counter < 7

    await asyncio.sleep(0.5, loop=event_loop)

    assert 4 < counter < 7


@pytest.mark.asyncio
async def test_long_func(event_loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(0.5)

    periodic = PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    await asyncio.sleep(1, loop=event_loop)
    periodic.stop()

    assert 1 < counter < 3


@pytest.mark.asyncio
async def test_shield(event_loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(2)

    periodic = PeriodicCallback(task)
    periodic.start(0.1, event_loop, shield=True)

    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    assert counter == 1

    # No shield
    counter = 0
    periodic = PeriodicCallback(task)
    periodic.start(0.1, event_loop, shield=False)

    await asyncio.sleep(0)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    assert counter == 0
