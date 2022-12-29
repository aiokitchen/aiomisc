from asyncio import CancelledError, create_task, sleep
from contextlib import suppress

import pytest

from aiomisc import gather_independent
from tests.tests_gather.conftest import ok, fail, cancel


async def test_gather_nones():
    async def foo(val):
        return val

    res = await gather_independent(
        foo(4), None, foo(5), None,
    )
    assert res == [4, None, 5, None]


async def test_gather_tasks():
    async def foo(val):
        return val

    res = await gather_independent(create_task(foo(2)))
    assert res == [2]


async def test_gather_empty():
    assert not await gather_independent()


async def test_gather_ok():
    stask1 = create_task(ok())
    stask2 = create_task(ok())

    await gather_independent(stask1, stask2)
    assert stask1.done() and await stask1
    assert stask2.done() and await stask2


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_gather_secondary_failed(wait_cancelled):
    stask1 = create_task(fail())
    stask2 = create_task(ok(0.01))

    await gather_independent(
        stask1, stask2,
        wait_cancelled=wait_cancelled,
    )
    assert stask1.exception()
    assert stask2.done() and not stask2.cancelled()


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_gather_secondary_cancelled(wait_cancelled):
    stask1 = create_task(cancel())
    stask2 = create_task(ok(0.01))

    await gather_independent(
        stask1, stask2,
        wait_cancelled=wait_cancelled,
    )
    assert stask1.cancelled()
    assert stask2.done() and not stask2.cancelled()


async def test_gather_external_cancel_no_wait():
    task = create_task(ok(100))
    gtask = create_task(gather_independent(task))

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
    gtask = create_task(gather_independent(task))

    await sleep(0.01)
    assert not task.done()

    gtask.cancel()
    await sleep(0.005)
    assert not task.done()
    await sleep(0.01)
    assert task.done()
    with pytest.raises(CancelledError):
        await gtask
