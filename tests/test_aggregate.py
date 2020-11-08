import asyncio
import math
from asyncio import create_task, wait
from typing import List

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


async def test_error():

    leeway = 0.01

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> List[float]:
        raise ValueError

    async def pho(num: float):
        return await pow(num)

    tasks = []
    for i in range(10):
        tasks.append(create_task(pho(i)))

    await asyncio.sleep(leeway * 1.5)

    assert tasks
    for task in tasks:
        assert task.done()
        assert isinstance(task.exception(), ValueError)


async def test_leeway():

    leeway = 0.1

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> List[float]:
        return [math.pow(num, power) for num in args]

    async def pho(num: float):
        return await pow(num)

    tasks = []
    for i in range(9):
        tasks.append(create_task(pho(i)))
        await asyncio.sleep(leeway / 10 * 0.95)

    assert all(not task.done() for task in tasks)

    await asyncio.sleep(leeway / 10)
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count():
    leeway = 0.1
    max_count = 5

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> List[float]:
        return [math.pow(num, power) for num in args]

    async def pho(num: float):
        return await pow(num)

    tasks = []
    for i in range(9):
        tasks.append(create_task(pho(i)))
        await asyncio.sleep(leeway / 10)

    for i in range(5):
        assert tasks[i].done()
    for i in range(5, 9):
        assert not tasks[i].done()

    await asyncio.sleep(leeway * 7 / 10)
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)
