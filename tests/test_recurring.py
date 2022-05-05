import asyncio

import pytest

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_delayed(loop):
    condition = asyncio.Condition()
    counter = 0

    async def task():
        nonlocal counter
        counter += 1

        async with condition:
            condition.notify_all()

    recurring = aiomisc.RecurringCallback(task)
    task = recurring.start(strategy=lambda _: 0, loop=loop)

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: counter >= 5),
            timeout=5,
        )

    await aiomisc.cancel_tasks([task])


async def test_long_func(loop):
    counter = 0
    condition = asyncio.Condition()

    async def task():
        nonlocal counter
        async with condition:
            await asyncio.sleep(0.5)
            counter += 1
            condition.notify_all()

    recurring = aiomisc.RecurringCallback(task)
    task = recurring.start(strategy=lambda _: 0, loop=loop)

    await asyncio.sleep(1.2)
    await aiomisc.cancel_tasks([task])

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: counter >= 2),
            timeout=2,
        )

    assert counter == 2


@aiomisc.timeout(5)
async def test_shield(loop):
    counter = 0
    start_event = asyncio.Event()
    stop_event = asyncio.Event()

    async def task():
        nonlocal counter
        start_event.set()
        await asyncio.sleep(0.5)
        counter += 1
        stop_event.set()

    recurring = aiomisc.RecurringCallback(task)
    task = recurring.start(strategy=lambda _: 0, loop=loop, shield=True)

    await start_event.wait()
    await aiomisc.cancel_tasks([task])
    await stop_event.wait()
    assert counter == 1
