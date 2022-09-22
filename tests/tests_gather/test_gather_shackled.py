from asyncio import CancelledError, create_task, sleep
from contextlib import suppress

import pytest

from aiomisc import gather_shackled
from tests.tests_gather.conftest import ok, fail, cancel


async def test_gather_nones():
    async def foo(val):
        return val

    res = await gather_shackled(foo(1), foo(2), None, None, foo(3))
    assert res == [1, 2, None, None, 3]


async def test_gather_tasks():
    async def foo(val):
        return val

    res = await gather_shackled(create_task(foo(1)))
    assert res == [1]


async def test_gather_empty():
    assert not await gather_shackled()


async def test_gather_ok():
    ptask1 = create_task(ok())
    ptask2 = create_task(ok())

    await gather_shackled(ptask1, ptask2)
    assert ptask1.done() and await ptask1
    assert ptask2.done() and await ptask2


async def test_gather_failed_no_wait():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))

    with pytest.raises(ValueError):
        await gather_shackled(ptask1, ptask2)

    assert ptask1.exception()
    assert not ptask2.done()
    await sleep(0.01)
    assert ptask2.cancelled()


async def test_gather_failed_wait_cancelled():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))

    with pytest.raises(ValueError):
        await gather_shackled(ptask1, ptask2, wait_cancelled=True)

    assert ptask1.exception()
    assert ptask2.cancelled()


async def test_gather_cancelled_no_wait():
    ptask1 = create_task(cancel())
    ptask2 = create_task(ok(100))

    with pytest.raises(CancelledError):
        await gather_shackled(ptask1, ptask2)

    assert ptask1.cancelled()
    assert not ptask2.done()
    await sleep(0.01)
    assert ptask2.cancelled()


async def test_gather_cancelled_wait_cancelled():
    async def cancel():
        raise CancelledError

    async def ok():
        await sleep(100)

    ptask1 = create_task(cancel())
    ptask2 = create_task(ok())

    with pytest.raises(CancelledError):
        await gather_shackled(ptask1, ptask2, wait_cancelled=True)

    assert ptask1.cancelled()
    assert ptask2.cancelled()


async def test_gather_external_cancel_no_wait():
    task = create_task(ok(100))
    gtask = create_task(gather_shackled(task))

    await sleep(0.01)
    assert not task.done()

    gtask.cancel()
    await sleep(0.01)
    assert task.cancelled()
    with pytest.raises(CancelledError):
        await gtask


async def test_gather_external_cancel_wait_cancelled():
    async def cancel():
        with suppress(CancelledError):
            await sleep(100)
        await sleep(0.01)

    task = create_task(cancel())
    gtask = create_task(gather_shackled(task))

    await sleep(0.01)
    assert not task.done()

    gtask.cancel()
    await sleep(0.005)
    assert not task.done()
    await sleep(0.01)
    assert task.done()
    with pytest.raises(CancelledError):
        await gtask
