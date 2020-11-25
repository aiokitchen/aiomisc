import asyncio
import math
from time import monotonic
from typing import List

from aiocontextvars import ContextVar
import pytest

from aiomisc.aggregate import aggregate


async def test_invalid_func():
    with pytest.raises(ValueError) as excinfo:
        @aggregate(10)
        async def pho(a, b=1):
            pass
    assert str(excinfo.value) == (
        "Function must accept variadic positional arguments"
    )


@pytest.mark.parametrize('leeway_ms', (-1.0, 0.0))
async def test_invalid_leeway(leeway_ms):
    with pytest.raises(ValueError) as excinfo:
        @aggregate(leeway_ms)
        async def pho(*args):
            pass

    assert str(excinfo.value) == "leeway_ms must be positive float"


@pytest.mark.parametrize('max_count', (-1, 0))
async def test_invalid_max_count(max_count):
    with pytest.raises(ValueError) as excinfo:
        @aggregate(10, max_count)
        async def pho(*args):
            pass

    assert str(excinfo.value) == "max_count must be positive int or None"


async def test_error(loop):
    leeway = 0.01

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> List[float]:
        raise ValueError

    async def pho(num: int):
        return await pow(float(num))

    tasks = []
    for i in range(10):
        tasks.append(loop.create_task(pho(i)))

    await asyncio.sleep(leeway * 1.5)

    assert tasks
    for task in tasks:
        assert task.done()
        assert isinstance(task.exception(), ValueError)


async def test_leeway_ok(loop):
    leeway = 0.1

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> List[float]:
        return [math.pow(num, power) for num in args]

    tasks = []
    now = monotonic()
    for i in range(9):
        tasks.append(loop.create_task(pow(i)))
        await asyncio.sleep(leeway / 10 * 0.9)
    assert all(not task.done() for task in tasks)

    await asyncio.sleep(leeway * 2 / 10)
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count(loop):
    leeway = 0.1
    max_count = 5

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> List[float]:
        return [math.pow(num, power) for num in args]

    tasks = []
    for i in range(5):
        tasks.append(loop.create_task(pow(i)))

    await asyncio.sleep(leeway / 10)

    for i, task in enumerate(tasks):
        assert tasks[i].done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_multiple_batches(loop):
    leeway = 0.1
    max_count = 5

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> List[float]:
        return [math.pow(num, power) for num in args]

    tasks = []
    for i in range(9):
        tasks.append(loop.create_task(pow(i)))
        await asyncio.sleep(leeway / 10)

    for i in range(5):
        assert tasks[i].done()
    for i in range(5, 9):
        assert not tasks[i].done()

    await asyncio.sleep(leeway * 7 / 10)
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_leeway_cancel(loop):
    executions = 0
    leeway = 0.1
    arg = ContextVar('arg')
    tasks = []
    executing_task = None

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> List[float]:
        nonlocal executions, executing_task
        executions += 1
        executing_task = tasks[arg.get()]
        await asyncio.sleep(leeway)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    for i in range(9):
        tasks.append(loop.create_task(pho(i)))
        await asyncio.sleep(leeway / 10 * 0.95)

    assert all(not task.done() for task in tasks)

    # Execution must have started
    await asyncio.sleep(leeway / 10)
    assert executions == 1
    first_executing_task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await asyncio.sleep(leeway / 10)
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks
        if task is not first_executing_task
    )

    # Must have finished
    await asyncio.sleep(leeway)
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_cancel(loop):
    executions = 0
    leeway = 100
    max_count = 5
    arg = ContextVar('arg')
    tasks = []
    executing_task = None

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> List[float]:
        nonlocal executions, executing_task
        executions += 1
        executing_task = tasks[arg.get()]
        await asyncio.sleep(0.1)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    tasks = []
    for i in range(5):
        tasks.append(loop.create_task(pho(i)))

    await asyncio.sleep(0.01)

    # Execution must have started
    assert all(not task.done() for task in tasks)
    assert executions == 1
    first_executing_task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await asyncio.sleep(0.01)
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks
        if task is not first_executing_task
    )

    # Must have finished
    await asyncio.sleep(0.1)
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_multiple_batches_cancel(loop):
    executions = 0
    leeway = 0.1
    max_count = 5
    arg = ContextVar('arg')
    tasks = []
    executing_task = None

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> List[float]:
        nonlocal executions, executing_task
        executions += 1
        executing_task = tasks[arg.get()]
        await asyncio.sleep(leeway)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    tasks = []
    for i in range(9):
        tasks.append(loop.create_task(pho(i)))
        await asyncio.sleep(leeway / 10)

    # Execution of the first batch must have started
    assert all(not task.done() for task in tasks)
    assert executions == 1
    first_executing_task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await asyncio.sleep(leeway / 10)
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks
        if task is not first_executing_task
    )

    # First batch must have finished
    await asyncio.sleep(leeway)
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks[:5]):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)

    # Second batch must have started execution
    assert all(not task.done() for task in tasks[5:])
    assert executions == 3

    # Second batch mast have finished
    await asyncio.sleep(leeway)
    for i, task in enumerate(tasks[5:], start=5):
        assert task.done()
        assert task.result() == math.pow(i, 2)
