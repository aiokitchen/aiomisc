import asyncio
import logging
import math
import platform
import time
from asyncio import Event, wait
from contextvars import ContextVar
from typing import Any, List
from collections.abc import Sequence

import pytest

from aiomisc.aggregate import Arg, ResultNotSetError, aggregate, aggregate_async

log = logging.getLogger(__name__)

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Skip flapping tests on windows because it "
    "system timer hasn't enough resolution",
)


@pytest.fixture(scope="session")
def leeway() -> float:
    async def func() -> float:
        loop = asyncio.get_event_loop()
        t = loop.time()
        await asyncio.sleep(0)
        return loop.time() - t

    async def run() -> Sequence[float]:
        tasks = [asyncio.create_task(func()) for _ in range(100)]
        return await asyncio.gather(*tasks)

    ts: Sequence[float] = asyncio.run(run())
    estimated = max(ts) * 5
    default = 0.1
    result = max(estimated, default)

    if estimated > default:
        log.warning("Slow system: leeway increased to %.2f s", result)

    return result


async def test_invalid_func():
    with pytest.raises(ValueError) as excinfo:

        @aggregate(10)
        async def pho(a, b=1):
            pass

    assert str(excinfo.value) == (
        "Function must accept variadic positional arguments"
    )


@pytest.mark.parametrize("leeway_ms", (-1.0, 0.0))
async def test_invalid_leeway(leeway_ms):
    with pytest.raises(ValueError) as excinfo:

        @aggregate(leeway_ms)
        async def pho(*args):
            pass

    assert str(excinfo.value) == "leeway_ms must be positive float"


@pytest.mark.parametrize("max_count", (-1, 0))
async def test_invalid_max_count(max_count):
    with pytest.raises(ValueError) as excinfo:

        @aggregate(10, max_count)
        async def pho(*args):
            pass

    assert str(excinfo.value) == "max_count must be positive int or None"


async def test_error(event_loop, leeway):
    event = Event()

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> Any:
        event.set()
        raise ValueError

    async def pho(num: int):
        return await pow(float(num))

    tasks = []
    for i in range(10):
        tasks.append(event_loop.create_task(pho(i)))

    await event.wait()

    await wait(tasks)
    for task in tasks:
        assert task.done()
        assert isinstance(task.exception(), ValueError)


async def test_leeway_ok(event_loop, leeway):
    t_exec: float = 0.0
    event: Event = Event()

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal t_exec
        t_exec = time.time()
        event.set()

        return [math.pow(num, power) for num in args]

    tasks = []
    for i in range(9):
        tasks.append(event_loop.create_task(pow(i)))

    t = time.time()

    await asyncio.sleep(leeway * 0.1)
    assert all(not task.done() for task in tasks)

    await event.wait()
    elapsed = t_exec - t
    assert leeway * 0.9 < elapsed < leeway * 2

    await wait(tasks)
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count(event_loop, leeway):
    t_exec: float = 0.0
    event = Event()
    max_count = 5

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal t_exec
        t_exec = time.time()
        event.set()

        return [math.pow(num, power) for num in args]

    tasks = []
    for i in range(5):
        tasks.append(event_loop.create_task(pow(i)))

    t = time.time()

    await event.wait()
    elapsed = t_exec - t
    assert 0 < elapsed < leeway * 2

    await wait(tasks)
    for i, task in enumerate(tasks):
        assert tasks[i].done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_multiple_batches(event_loop, leeway):
    t_exec: float = 0.0
    event = Event()
    max_count = 5

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal t_exec
        t_exec = time.time()
        event.set()

        return [math.pow(num, power) for num in args]

    tasks = []
    for i in range(9):
        tasks.append(event_loop.create_task(pow(i)))

    t = time.time()

    # Wait for the first batch
    await event.wait()
    event.clear()
    elapsed = t_exec - t
    assert 0 < elapsed < leeway

    await wait(tasks[:5])
    for i in range(5):
        assert tasks[i].done()
    for i in range(5, 9):
        assert not tasks[i].done()

    tasks.append(event_loop.create_task(pow(9)))

    # Wait for the second batch
    await event.wait()
    await wait(tasks[5:])
    for i, task in enumerate(tasks):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_leeway_cancel(event_loop, leeway):
    t_exec: float = 0.0
    delay_exec = 0.1
    event = Event()
    executions = 0
    arg: ContextVar = ContextVar("arg")
    tasks: list[asyncio.Task] = []
    executing_task: asyncio.Task

    @aggregate(leeway * 1000)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal executions, executing_task, t_exec, delay_exec
        t_exec = time.time()
        executions += 1
        executing_task = tasks[arg.get()]
        event.set()

        await asyncio.sleep(delay_exec)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    for i in range(9):
        tasks.append(event_loop.create_task(pho(i)))

    t = time.time()

    # Execution must have started
    await event.wait()
    event.clear()
    elapsed = t_exec - t
    assert leeway * 0.9 < elapsed < leeway * 2
    assert executions == 1
    first_executing_task: asyncio.Task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await event.wait()
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks if task is not first_executing_task
    )

    # Must have finished
    await wait(tasks)
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_cancel(event_loop):
    t_exec: float = 0.0
    delay_exec = 0.1
    event = Event()
    executions = 0
    leeway = 100
    max_count = 5
    arg: ContextVar = ContextVar("arg")
    tasks: list[asyncio.Task] = []
    executing_task: asyncio.Task

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal executions, executing_task, t_exec, delay_exec
        t_exec = time.time()
        executions += 1
        executing_task = tasks[arg.get()]
        event.set()

        await asyncio.sleep(delay_exec)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    tasks = []
    for i in range(5):
        tasks.append(event_loop.create_task(pho(i)))

    t = time.time()

    # Execution must have started
    await event.wait()
    event.clear()
    elapsed = t_exec - t
    assert 0 < elapsed < leeway
    assert all(not task.done() for task in tasks)
    assert executions == 1
    first_executing_task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await event.wait()
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks if task is not first_executing_task
    )

    # Must have finished
    await wait(tasks)
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_max_count_multiple_batches_cancel(event_loop, leeway):
    delay_exec = 0.1
    event = Event()
    executions = 0
    max_count = 5
    arg: ContextVar = ContextVar("arg")
    tasks: list[asyncio.Task] = []
    executing_task: asyncio.Task

    @aggregate(leeway * 1000, max_count)
    async def pow(*args: float, power: float = 2) -> list[float]:
        nonlocal executions, executing_task, delay_exec
        executions += 1
        executing_task = tasks[arg.get()]
        event.set()

        await asyncio.sleep(delay_exec)
        return [math.pow(num, power) for num in args]

    async def pho(num: int):
        arg.set(num)
        return await pow(float(num))

    tasks = []
    for i in range(9):
        tasks.append(event_loop.create_task(pho(i)))

    # Execution of the first batch must have started
    await event.wait()
    event.clear()
    assert all(not task.done() for task in tasks)
    assert executions == 1
    first_executing_task = executing_task
    first_executing_task.cancel()

    # Another task must have tried to execute
    await event.wait()
    event.clear()
    assert executions == 2
    assert first_executing_task.cancelled()
    assert all(
        not task.done() for task in tasks if task is not first_executing_task
    )

    await wait(tasks[:5])
    # First batch must have finished
    assert first_executing_task.cancelled()
    for i, task in enumerate(tasks[:5]):
        if task is first_executing_task:
            continue
        assert task.done()
        assert task.result() == math.pow(i, 2)

    tasks.append(event_loop.create_task(pho(9)))
    # Second batch must have started execution
    await event.wait()
    assert all(not task.done() for task in tasks[5:])
    assert executions == 3

    # Second batch mast have finished
    await wait(tasks[5:])
    for i, task in enumerate(tasks[5:], start=5):
        assert task.done()
        assert task.result() == math.pow(i, 2)


async def test_low_level_sloppy(event_loop, leeway):
    max_count = 2

    @aggregate_async(leeway * 1000, max_count=max_count)
    async def pho(*args: Arg):
        for arg in args:
            if arg.value:
                arg.future.set_result(True)

    task1 = event_loop.create_task(pho(True))
    task2 = event_loop.create_task(pho(False))
    await wait([task1, task2])

    assert task1.done()
    assert await task1
    assert task2.done()
    assert isinstance(task2.exception(), ResultNotSetError)


async def test_low_level_ok(event_loop, leeway):
    @aggregate_async(leeway * 1000)
    async def pow(*args: Arg, power: float = 2):
        for arg in args:
            arg.future.set_result(math.pow(arg.value, power))

    tasks = []
    for i in range(5):
        tasks.append(event_loop.create_task(pow(i)))

    await wait(tasks)
    for i, task in enumerate(tasks):
        assert tasks[i].done()
        assert task.result() == math.pow(i, 2)


async def test_low_level_error(event_loop, leeway):
    @aggregate_async(leeway * 1000)
    async def pho(*args: Arg):
        for arg in args:
            if arg.value:
                arg.future.set_result(True)
            else:
                arg.future.set_exception(ValueError)

    task1 = event_loop.create_task(pho(True))
    task2 = event_loop.create_task(pho(False))
    await wait([task1, task2])

    assert task1.done()
    assert task1.result()
    assert task2.done()
    assert isinstance(task2.exception(), ValueError)
