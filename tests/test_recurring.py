import asyncio

import pytest

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_recurring(loop):
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


@aiomisc.timeout(5)
async def test_control_flow_stop(loop):
    stop_event = asyncio.Event()

    async def strategy(_: aiomisc.RecurringCallback):
        stop_event.set()
        raise aiomisc.StrategyStop()

    recurring = aiomisc.RecurringCallback(lambda: None)
    task = recurring.start(strategy=strategy, loop=loop)

    await stop_event.wait()
    await task


@aiomisc.timeout(5)
async def test_control_flow_skip(loop):
    start_event = asyncio.Event()
    stop_event = asyncio.Event()
    counter = 0
    strategy_counter = 0

    async def task():
        nonlocal counter
        counter += 1
        start_event.set()

    async def strategy(_: aiomisc.RecurringCallback):
        nonlocal strategy_counter

        strategy_counter += 1

        if strategy_counter == 3:
            raise aiomisc.StrategySkip(0)

        if strategy_counter == 5:
            stop_event.set()
            raise aiomisc.StrategyStop()

        return 0

    recurring = aiomisc.RecurringCallback(task)
    task = recurring.start(strategy=strategy, loop=loop)

    await start_event.wait()
    await stop_event.wait()
    await task

    assert counter == 3
    assert strategy_counter == 5


@aiomisc.timeout(5)
async def test_wrong_strategy(loop):
    counter = 0
    strategy_counter = 0

    async def task():
        nonlocal counter
        counter += 1

    async def strategy(_: aiomisc.RecurringCallback):
        nonlocal strategy_counter
        strategy_counter += 1
        return None

    recurring = aiomisc.RecurringCallback(task)
    task = recurring.start(strategy=strategy, loop=loop)

    await task
    assert strategy_counter == 1
    assert counter == 0
