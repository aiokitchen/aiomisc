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

    await asyncio.sleep(0.5)
    periodic.stop()

    assert 4 < counter < 7

    await asyncio.sleep(0.5)

    assert 4 < counter < 7


async def test_long_func(loop):
    counter = 0

    async def task():
        nonlocal counter
        counter += 1
        await asyncio.sleep(0.5)

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop)

    await asyncio.sleep(1)
    periodic.stop()

    assert 1 < counter < 3


async def test_shield(loop):
    counter = 0

    async def task():
        nonlocal counter
        await asyncio.sleep(0.1)
        counter += 1

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.2, loop, shield=True)

    # Wait for periodic callback to start
    await asyncio.sleep(0.01)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    # Wait for counter to increment
    await asyncio.sleep(0.1)

    # Shielded
    assert counter == 1

    # No shield
    counter = 0
    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.2, loop, shield=False)

    # Wait for periodic callback to start
    await asyncio.sleep(0.01)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    # Wait for counter to increment
    await asyncio.sleep(0.1)

    # Cancelled
    assert counter == 0


async def test_delay(loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, loop, delay=0.5)

    await asyncio.sleep(0.25)

    assert not counter

    await asyncio.sleep(0.5)

    periodic.stop()

    assert 1 < counter < 4
