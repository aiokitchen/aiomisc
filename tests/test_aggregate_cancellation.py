import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import pytest

from aiomisc.aggregate import Arg, aggregate, aggregate_async


pytestmark = pytest.mark.catch_loop_exceptions


@pytest.fixture
async def spawn():
    tasks = []

    def create(coroutine: Coroutine[Any, Any, Any]) -> asyncio.Task:
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    try:
        yield create
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.fixture(
    params=(aggregate, aggregate_async), ids=("aggregate", "aggregate_async")
)
def make_aggregate(request, binding):
    low_level = request.param is aggregate_async

    def make(handler: Callable[..., Any], *, max_count=3):
        async def backend(*args, **kwargs):
            values = tuple(item.value if low_level else item for item in args)
            results = await handler(values, kwargs)
            if low_level:
                for item, result in zip(args, results):
                    if not item.future.done():
                        item.future.set_result(result)
            return results

        func: Any = backend
        if binding == "static":
            func = staticmethod(backend)
        elif binding != "module":

            async def method(receiver, *args, **kwargs):
                return await backend(*args, **kwargs)

            func = classmethod(method) if binding == "class" else method

        decorated = request.param(60_000, max_count=max_count)(func)
        if binding == "module":
            return decorated

        class Owner:
            load = decorated

        return Owner().load if binding == "instance" else Owner.load

    return make


@pytest.fixture(params=("module", "instance", "class", "static"))
def binding(request):
    return request.param


async def started(event):
    await asyncio.wait_for(event.wait(), timeout=5)


async def cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, timeout=5)


async def results(*tasks):
    return await asyncio.wait_for(asyncio.gather(*tasks), timeout=5)


@pytest.mark.parametrize("position", (0, 1, 3), ids=("first", "middle", "last"))
async def test_cancel_collecting_item_preserves_order(
    make_aggregate, spawn, position
):
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        return [value * 10 for value in values]

    load = make_aggregate(backend, max_count=5)
    tasks = [spawn(load(value, key="same")) for value in range(4)]
    await asyncio.sleep(0)
    assert load.__self__.count == 4
    await cancel(tasks[position])
    expected = [value for value in range(4) if value != position] + [4, 5]
    assert load.__self__.count == 3
    tasks.extend(spawn(load(value, key="same")) for value in (4, 5))
    surviving = [task for index, task in enumerate(tasks) if index != position]
    assert await results(*surviving) == [value * 10 for value in expected]
    assert batches == [tuple(expected)]
    assert not load.__self__._buckets


@pytest.mark.parametrize("position", (0, 1), ids=("first", "middle"))
async def test_cancel_running_waiter_preserves_order(
    make_aggregate, spawn, position
):
    entered = asyncio.Event()
    release = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        entered.set()
        await release.wait()
        return [value * 10 for value in values]

    load = make_aggregate(backend)
    tasks = [spawn(load(value)) for value in range(3)]
    await started(entered)
    await cancel(tasks[position])
    surviving = [task for index, task in enumerate(tasks) if index != position]
    assert all(not task.done() for task in surviving)
    release.set()
    assert await results(*surviving) == [
        value * 10 for value in range(3) if value != position
    ]
    assert batches == [(0, 1, 2)]
    assert load.__self__.count == 0
    assert await results(*(spawn(load(value)) for value in (3, 4, 5))) == [
        30,
        40,
        50,
    ]
    assert batches == [(0, 1, 2), (3, 4, 5)]


async def test_cancel_executor_retries_once(make_aggregate, spawn):
    entered = asyncio.Event()
    retry = asyncio.Event()
    release = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        (entered if len(batches) == 1 else retry).set()
        await release.wait()
        return [value * 10 for value in values]

    load = make_aggregate(backend)
    tasks = [spawn(load(value)) for value in range(3)]
    await started(entered)
    await cancel(tasks[2])
    await started(retry)
    assert not tasks[0].done() and not tasks[1].done()
    release.set()
    assert await results(*tasks[:2]) == [0, 10]
    assert batches == [(0, 1, 2), (0, 1, 2)]
    assert load.__self__._statistic.done == 2
    assert load.__self__._statistic.success == 1
    assert load.__self__._statistic.error == 0
    assert not load.__self__._buckets


async def test_cancel_executor_after_partial_results(spawn):
    entered = asyncio.Event()
    retry = asyncio.Event()
    release = asyncio.Event()
    batches = []

    @aggregate_async(60_000, max_count=3)
    async def load(*items: Arg[int, int]):
        batches.append(tuple(item.value for item in items))
        if len(batches) == 1:
            items[0].future.set_result(0)
            entered.set()
        else:
            retry.set()
        await release.wait()
        for item in items:
            if not item.future.done():
                item.future.set_result(item.value * 10)

    tasks = [spawn(load(value)) for value in range(3)]
    await started(entered)
    await cancel(tasks[2])
    await started(retry)
    assert await results(tasks[0]) == [0]
    assert not tasks[1].done()
    release.set()
    assert await results(tasks[1]) == [10]
    assert batches == [(0, 1, 2), (0, 1, 2)]


async def test_cancel_successive_executors(make_aggregate, spawn):
    executions: asyncio.Queue[asyncio.Task[Any]] = asyncio.Queue()
    release = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        executor = asyncio.current_task()
        assert executor is not None
        executions.put_nowait(executor)
        await release.wait()
        return [value * 10 for value in values]

    load = make_aggregate(backend)
    tasks = [spawn(load(value)) for value in range(3)]
    for _ in range(2):
        executor = await asyncio.wait_for(executions.get(), timeout=5)
        await cancel(executor)
    executor = await asyncio.wait_for(executions.get(), timeout=5)
    assert executor in tasks
    release.set()
    surviving = [task for task in tasks if not task.cancelled()]
    assert len(surviving) == 1
    index = tasks.index(surviving[0])
    assert await results(*surviving) == [index * 10]
    assert batches == [(0, 1, 2)] * 3
    assert load.__self__._statistic.done == 3
    assert load.__self__._statistic.success == 1
    assert load.__self__._statistic.error == 0
    assert not load.__self__._buckets


async def test_cancel_item_does_not_compare_values(make_aggregate, spawn):
    class Value:
        def __eq__(self, other):
            raise AssertionError("Cancellation must not compare item values")

    async def backend(values, kwargs):
        return [id(value) for value in values]

    load = make_aggregate(backend, max_count=4)
    values = [Value() for _ in range(5)]
    tasks = [spawn(load(value)) for value in values[:3]]
    await asyncio.sleep(0)
    await cancel(tasks[1])
    assert load.__self__.count == 2
    tasks.extend(spawn(load(value)) for value in values[3:])
    assert await results(tasks[0], *tasks[2:]) == [
        id(value) for index, value in enumerate(values) if index != 1
    ]
    assert not load.__self__._buckets


async def test_cancel_all_collecting_buckets(make_aggregate, spawn):
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        return list(values)

    load = make_aggregate(backend)
    tasks = [
        spawn(load(value, key=key)) for key in range(32) for value in range(2)
    ]
    await asyncio.sleep(0)
    assert load.__self__.count == 64
    assert len(load.__self__._buckets) == 32
    for task in tasks:
        task.cancel()
    cancelled = await asyncio.wait_for(
        asyncio.gather(*tasks, return_exceptions=True), 5
    )
    assert all(
        isinstance(result, asyncio.CancelledError) for result in cancelled
    )
    assert load.__self__.count == 0
    assert not load.__self__._buckets
    assert not batches
    assert load.__self__._statistic.done == 0
    assert await results(
        *(spawn(load(value, key=0)) for value in (2, 3, 4))
    ) == [2, 3, 4]
    assert batches == [(2, 3, 4)]


async def test_cancel_all_running_calls_does_not_retry(make_aggregate, spawn):
    entered = asyncio.Event()
    release = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        entered.set()
        await release.wait()
        return list(values)

    load = make_aggregate(backend)
    tasks = [spawn(load(value)) for value in range(3)]
    await started(entered)
    await cancel(tasks[1])
    await cancel(tasks[0])
    await cancel(tasks[2])
    assert batches == [(0, 1, 2)]
    assert load.__self__._statistic.done == 1
    assert load.__self__._statistic.success == 0
    assert load.__self__._statistic.error == 0
    assert not load.__self__._buckets
    release.set()
    assert await results(*(spawn(load(value)) for value in (3, 4, 5))) == [
        3,
        4,
        5,
    ]
    assert batches == [(0, 1, 2), (3, 4, 5)]


async def test_cancel_old_batch_preserves_new_bucket(make_aggregate, spawn):
    entered = asyncio.Event()
    release = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append((kwargs["key"], values))
        if values[0] == 0:
            entered.set()
            await release.wait()
        return [value * 10 for value in values]

    load = make_aggregate(backend)
    old = [spawn(load(value, key="same")) for value in range(3)]
    await started(entered)
    new = [spawn(load(value, key="same")) for value in (3, 4)]
    await asyncio.sleep(0)
    assert load.__self__.count == 2
    await cancel(old[1])
    assert load.__self__.count == 2
    new.append(spawn(load(5, key="same")))
    assert await results(*new) == [30, 40, 50]
    assert await results(
        *(spawn(load(value, key="other")) for value in (6, 7, 8))
    ) == [60, 70, 80]
    assert not old[0].done() and not old[2].done()
    release.set()
    assert await results(old[0], old[2]) == [0, 20]
    assert batches == [
        ("same", (0, 1, 2)),
        ("same", (3, 4, 5)),
        ("other", (6, 7, 8)),
    ]
    assert not load.__self__._buckets


async def test_error_after_middle_waiter_cancelled(make_aggregate, spawn):
    entered = asyncio.Event()
    release = asyncio.Event()
    error = LookupError("batch failed")

    async def backend(values, kwargs):
        if values[0] == 0:
            entered.set()
            await release.wait()
            raise error
        return list(values)

    load = make_aggregate(backend)
    tasks = [spawn(load(value)) for value in range(3)]
    await started(entered)
    await cancel(tasks[1])
    release.set()
    failures = await asyncio.wait_for(
        asyncio.gather(tasks[0], tasks[2], return_exceptions=True), 5
    )
    assert failures == [error, error]
    assert load.__self__._statistic.done == 1
    assert load.__self__._statistic.success == 0
    assert load.__self__._statistic.error == 1
    assert not load.__self__._buckets
    assert await results(*(spawn(load(value)) for value in (3, 4, 5))) == [
        3,
        4,
        5,
    ]


async def test_cancel_taskgroup_clears_bucket(make_aggregate, spawn):
    ready = asyncio.Event()
    batches = []

    async def backend(values, kwargs):
        batches.append(values)
        return list(values)

    load = make_aggregate(backend, max_count=7)

    async def parent():
        async with asyncio.TaskGroup() as group:
            for value in range(6):
                group.create_task(load(value))
            await asyncio.sleep(0)
            assert load.__self__.count == 6
            ready.set()
            await asyncio.Future()

    task = spawn(parent())
    await started(ready)
    await cancel(task)
    assert not load.__self__._buckets
    assert load.__self__.count == 0
    assert not batches
    assert await results(*(spawn(load(value)) for value in range(7))) == list(
        range(7)
    )


async def test_cancel_taskgroup_running_batch(make_aggregate, spawn):
    entered = asyncio.Event()
    release = asyncio.Event()
    batches = []
    children: list[asyncio.Task[Any]] = []

    async def backend(values, kwargs):
        batches.append(values)
        entered.set()
        await release.wait()
        return list(values)

    load = make_aggregate(backend)

    async def parent():
        async with asyncio.TaskGroup() as group:
            children.extend(
                group.create_task(load(value)) for value in range(3)
            )

    task = spawn(parent())
    await started(entered)
    await cancel(task)
    assert all(child.cancelled() for child in children)
    assert batches == [(0, 1, 2)]
    assert not load.__self__._buckets
    release.set()
    assert await results(*(spawn(load(value)) for value in (3, 4, 5))) == [
        3,
        4,
        5,
    ]
    assert batches == [(0, 1, 2), (3, 4, 5)]


@pytest.mark.parametrize(
    "max_count", (None, 5), ids=("unlimited", "incomplete")
)
async def test_cancel_middle_before_timeout(
    make_aggregate, spawn, monkeypatch, max_count
):
    timeouts = []
    timeout_at = asyncio.timeout_at
    batches = []

    def capture(deadline):
        timeout = timeout_at(deadline)
        timeouts.append(timeout)
        return timeout

    monkeypatch.setattr(asyncio, "timeout_at", capture)

    async def backend(values, kwargs):
        batches.append(values)
        return [value * 10 for value in values]

    load = make_aggregate(backend, max_count=max_count)
    tasks = [spawn(load(value)) for value in range(3)]
    await asyncio.sleep(0)
    assert len(timeouts) == 3
    await cancel(tasks[1])
    assert load.__self__.count == 2
    deadline = asyncio.get_running_loop().time() - 1
    timeouts[0].reschedule(deadline)
    timeouts[2].reschedule(deadline)
    assert await results(tasks[0], tasks[2]) == [0, 20]
    assert batches == [(0, 2)]
    assert not load.__self__._buckets
