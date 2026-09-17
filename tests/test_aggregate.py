import asyncio
import copy
import gc
import inspect
import logging
import math
import platform
import pickle
import time
import weakref
from asyncio import Event, wait
from contextvars import ContextVar
from typing import Any, List, assert_type
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


async def test_aggregate_kwargs():
    @aggregate(10_000, max_count=2)
    async def power(*args: int, exponent: int) -> list[int]:
        return [value**exponent for value in args]

    @aggregate_async(10_000, max_count=2)
    async def power_async(*args: Arg, exponent: int) -> None:
        for arg in args:
            arg.future.set_result(arg.value**exponent)

    calls: tuple[Any, ...] = (
        power(2, exponent=2),
        power(2, exponent=3),
        power(3, exponent=2),
        power(3, exponent=3),
    )
    async_calls: tuple[Any, ...] = (
        power_async(2, exponent=2),
        power_async(2, exponent=3),
        power_async(3, exponent=2),
        power_async(3, exponent=3),
    )

    assert await asyncio.gather(*calls) == [4, 8, 9, 27]
    assert await asyncio.gather(*async_calls) == [4, 8, 9, 27]
    with pytest.raises(TypeError, match="must be hashable"):
        await power(1, exponent=[])


async def test_aggregate_kwargs_order():
    batches = []

    @aggregate(10_000, max_count=2)
    async def surround(*args: str, prefix: str, suffix: str) -> list[str]:
        batches.append((args, prefix, suffix))
        return [f"{prefix}{value}{suffix}" for value in args]

    result: list[Any] = await asyncio.wait_for(
        asyncio.gather(
            surround("one", prefix="[", suffix="]"),
            surround("two", suffix="]", prefix="["),
        ),
        timeout=2,
    )

    assert result == ["[one]", "[two]"]
    assert batches == [(("one", "two"), "[", "]")]


async def test_aggregate_kwargs_isolate_exceptions():
    batches = []

    @aggregate(10_000, max_count=2)
    async def process(*args: int, fail: bool) -> list[int]:
        batches.append((fail, args))
        if fail:
            raise ValueError("failed batch")
        return list(args)

    result = await asyncio.wait_for(
        asyncio.gather(
            process(1, fail=False),
            process(2, fail=True),
            process(3, fail=False),
            process(4, fail=True),
            return_exceptions=True,
        ),
        timeout=2,
    )

    assert result[:3:2] == [1, 3]
    assert all(isinstance(result[index], ValueError) for index in (1, 3))
    assert set(batches) == {(False, (1, 3)), (True, (2, 4))}


async def test_aggregate_instance_methods():
    class Calculator:
        __hash__ = None  # type: ignore[assignment]

        def __init__(self, exponent: int) -> None:
            self.exponent = exponent

        @aggregate(10_000, max_count=2)
        async def power(self, *args: int) -> list[int]:
            return [value**self.exponent for value in args]

        @aggregate_async(10_000, max_count=2)
        async def power_async(self, *args: Arg) -> None:
            for arg in args:
                arg.future.set_result(arg.value**self.exponent)

    square = Calculator(2)
    cube = Calculator(3)

    assert await asyncio.gather(
        square.power(2), cube.power(2), square.power(3), cube.power(3)
    ) == [4, 8, 9, 27]
    assert await asyncio.gather(
        square.power_async(2),
        cube.power_async(2),
        square.power_async(3),
        cube.power_async(3),
    ) == [4, 8, 9, 27]


async def test_aggregate_class_methods():
    class Calculator:
        exponent = 1

        @aggregate(10_000, max_count=2)
        @classmethod
        async def aggregate_outer(cls, *args: int) -> list[int]:
            return [value**cls.exponent for value in args]

        @classmethod
        @aggregate(10_000, max_count=2)
        async def classmethod_outer(cls, *args: int) -> list[int]:
            return [value**cls.exponent for value in args]

    class Square(Calculator):
        exponent = 2

    class Cube(Calculator):
        exponent = 3

    for name in ("aggregate_outer", "classmethod_outer"):
        square = getattr(Square, name)
        cube = getattr(Cube, name)
        assert await asyncio.gather(square(2), cube(2), square(3), cube(3)) == [
            4,
            8,
            9,
            27,
        ]


async def test_aggregate_static_methods():
    class Calculator:
        @aggregate(10_000, max_count=2)
        @staticmethod
        async def aggregate_outer(*args: int) -> list[int]:
            return list(args)

        @staticmethod
        @aggregate(10_000, max_count=2)
        async def staticmethod_outer(*args: int) -> list[int]:
            return list(args)

    for name in ("aggregate_outer", "staticmethod_outer"):
        assert await asyncio.gather(
            getattr(Calculator, name)(1), getattr(Calculator(), name)(2)
        ) == [1, 2]


async def test_aggregate_slots_without_dict():
    class Calculator:
        __slots__ = ()

        @aggregate(1, max_count=1)
        async def power(self, *args: int) -> list[int]:
            return list(args)

    with pytest.raises(TypeError, match="writable __dict__"):
        await Calculator().power(1)


@pytest.mark.parametrize("low_level", (False, True))
@pytest.mark.parametrize("remaining", (False, True))
async def test_cancel_waiting_call(low_level, remaining):
    batches = []

    async def process(*args, key):
        values = tuple(arg.value if low_level else arg for arg in args)
        batches.append((key, values))
        if low_level:
            for arg in args:
                arg.future.set_result(arg.value)
        return values

    decorator = aggregate_async if low_level else aggregate
    batched = decorator(10_000, max_count=2)(process)
    stale = asyncio.create_task(batched("stale", key="one"))
    other = (
        asyncio.create_task(batched("other", key="two")) if remaining else None
    )
    await asyncio.sleep(0)
    aggregator = batched.__self__
    assert aggregator.count == 1 + remaining
    stale.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stale
    assert aggregator.count == remaining
    assert len(aggregator._buckets) == remaining
    fresh = asyncio.create_task(batched("fresh", key="one"))
    await asyncio.sleep(0)
    assert not fresh.done()
    assert await batched("next", key="one") == "next"
    assert await fresh == "fresh"
    if other is not None:
        assert await batched("last", key="two") == "last"
        assert await other == "other"
    assert all("stale" not in values for _, values in batches)
    assert aggregator.count == 0
    assert not aggregator._buckets


class CopyableLoader:
    def __init__(self, prefix="original"):
        self.prefix = prefix

    @aggregate(1, max_count=1)
    async def load(self, *keys: str) -> list[str]:
        """Load keys with this owner's prefix."""
        return [self.prefix + key for key in keys]


@pytest.mark.parametrize("clone", (copy.copy, copy.deepcopy, pickle.loads))
async def test_cached_method_copy(clone):
    original = CopyableLoader()
    assert await original.load("key") == "originalkey"
    copied = clone(
        pickle.dumps(original) if clone is pickle.loads else original
    )
    copied.prefix = "copy"
    assert await copied.load("key") == "copykey"
    assert await original.load("key") == "originalkey"
    assert copied.load.__self__ is not original.load.__self__


def test_cached_method_does_not_retain_owner():
    loader = CopyableLoader()
    _ = loader.load
    reference = weakref.ref(loader)
    del _
    gc.disable()
    try:
        del loader
        assert reference() is None
    finally:
        gc.enable()


async def test_unbound_method_requires_receiver():
    with pytest.raises(TypeError, match="require an instance"):
        await CopyableLoader.load("key")
    assert await CopyableLoader.load(CopyableLoader(), "key") == "originalkey"


@pytest.mark.parametrize("decorator", (aggregate, aggregate_async))
def test_coroutine_metadata(decorator):
    async def original(*keys: int, option: str = "default") -> list[int]:
        """Original documentation."""
        return list(keys)

    decorated = decorator(1)(original)
    assert inspect.iscoroutinefunction(decorated)
    assert asyncio.iscoroutinefunction(decorated)
    assert decorated.__doc__ == original.__doc__
    assert inspect.signature(decorated) == inspect.signature(original)

    class Loader:
        @decorator(1)
        async def load(self, *keys: int, option: str = "default") -> list[int]:
            """Method documentation."""
            return list(keys)

        @decorator(1)
        @classmethod
        async def class_load(cls, *keys: int) -> list[int]:
            """Class documentation."""
            return list(keys)

        @classmethod
        @decorator(1)
        async def outer_class_load(cls, *keys: int) -> list[int]:
            """Outer class documentation."""
            return list(keys)

        @decorator(1)
        @staticmethod
        async def static_load(*keys: int) -> list[int]:
            """Static documentation."""
            return list(keys)

        @staticmethod
        @decorator(1)
        async def outer_static_load(*keys: int) -> list[int]:
            """Outer static documentation."""
            return list(keys)

    loader = Loader()
    assert loader.load.__doc__ == "Method documentation."
    assert (
        str(inspect.signature(loader.load))
        == "(*keys: int, option: str = 'default') -> list[int]"
    )
    for method in (
        loader.load,
        Loader.class_load,
        Loader.outer_class_load,
        Loader.static_load,
        Loader.outer_static_load,
    ):
        assert inspect.iscoroutinefunction(method)
        assert method.__doc__
    assert loader.load.__self__.count == 0
    assert Loader.class_load.__self__.count == 0


async def test_aggregate_result_typing():
    @aggregate(1, max_count=1)
    async def load(*keys: int) -> list[str]:
        return [str(key) for key in keys]

    @aggregate_async(1, max_count=1)
    async def load_async(*keys: Arg[int, str]) -> None:
        for key in keys:
            key.future.set_result(str(key.value))

    assert_type(await load(1), str)
    assert_type(await load_async(1), str)
    assert_type(await CopyableLoader().load("key"), str)


async def test_cancel_one_waiter_preserves_batch():
    batches = []

    @aggregate(10_000, max_count=3)
    async def load(*keys: str) -> list[str]:
        batches.append(keys)
        return list(keys)

    stale = asyncio.create_task(load("stale"))
    survivor = asyncio.create_task(load("survivor"))
    await asyncio.sleep(0)
    stale.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stale
    assert load.__self__.count == 1
    assert await asyncio.gather(load("fresh"), load("next"), survivor) == [
        "fresh",
        "next",
        "survivor",
    ]
    assert batches == [("survivor", "fresh", "next")]


async def test_cancel_dispatched_waiter_keeps_result_order():
    started = asyncio.Event()
    finish = asyncio.Event()

    @aggregate(10_000, max_count=2)
    async def load(*keys: str) -> list[str]:
        started.set()
        await finish.wait()
        return list(keys)

    first = asyncio.create_task(load("first"))
    second = asyncio.create_task(load("second"))
    await started.wait()
    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
    finish.set()
    assert await second == "second"


async def test_non_weakrefable_owner():
    class Loader:
        __slots__ = ("__dict__",)

        @aggregate(1, max_count=1)
        async def load(self, *keys: int) -> list[int]:
            return list(keys)

    loader = Loader()
    assert await loader.load(1) == 1
    assert await copy.copy(loader).load(2) == 2
