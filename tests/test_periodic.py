import asyncio

import pytest

import aiomisc

pytestmark = pytest.mark.catch_loop_exceptions


async def test_periodic(event_loop):
    condition = asyncio.Condition()
    counter = 0

    async def task():
        nonlocal counter
        counter += 1

        async with condition:
            condition.notify_all()

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: counter >= 5), timeout=5
        )

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()


async def test_periodic_return_exceptions(event_loop):
    condition = asyncio.Condition()
    counter = 0

    async def task():
        nonlocal counter
        counter += 1

        async with condition:
            condition.notify_all()

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: counter >= 5), timeout=5
        )

    await periodic.stop(return_exceptions=True)


async def test_long_func(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            counter += 1
            await asyncio.sleep(0.5)
            condition.notify_all()

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    await asyncio.sleep(1)
    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: counter == 2), timeout=2
        )


async def test_shield(event_loop):
    counter = 0

    async def task():
        nonlocal counter
        await asyncio.sleep(0.1)
        counter += 1

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.2, event_loop, shield=True)

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
    periodic.start(0.2, event_loop, shield=False)

    # Wait for periodic callback to start
    await asyncio.sleep(0.01)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    # Wait for counter to increment
    await asyncio.sleep(0.1)

    # Cancelled
    assert counter == 0


async def test_delay(event_loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    periodic = aiomisc.PeriodicCallback(task)
    periodic.start(0.1, event_loop, delay=0.5)

    await asyncio.sleep(0.25)

    assert not counter

    await asyncio.sleep(0.5)

    with pytest.raises(asyncio.CancelledError):
        await periodic.stop()

    assert 1 < counter <= 4


async def test_restart(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    periodic = aiomisc.PeriodicCallback(task)

    for i in (5, 10, 15):
        periodic.start(0.1, event_loop)

        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == i), timeout=5
            )

        with pytest.raises(asyncio.CancelledError):
            await periodic.stop()

        assert counter == i


@aiomisc.timeout(10)
async def test_cancelled_callback(event_loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()
        raise asyncio.CancelledError

    periodic = aiomisc.PeriodicCallback(task)

    for i in (5, 10, 15):
        periodic.start(0.1, event_loop)

        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == i), timeout=5
            )

        with pytest.raises(asyncio.CancelledError):
            await periodic.stop()

        assert counter == i
