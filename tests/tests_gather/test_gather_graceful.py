from asyncio import CancelledError, create_task, sleep
from contextlib import suppress

import pytest

from aiomisc import gather_graceful
from tests.tests_gather.conftest import ok, fail, cancel


async def test_gather_nones():
    async def foo(val):
        return val

    primary, secondary = await gather_graceful(
        [foo(1), foo(2), None, None, foo(3)],
        secondary=[foo(4), None, foo(5), None],
    )
    assert primary == [1, 2, None, None, 3]
    assert secondary == [4, None, 5, None]


async def test_gather_tasks():
    async def foo(val):
        return val

    primary, secondary = await gather_graceful(
        [create_task(foo(1))], secondary=[create_task(foo(2))],
    )
    assert primary == [1]
    assert secondary == [2]


async def test_gather_empty():
    with pytest.raises(ValueError):
        await gather_graceful()


async def test_gather_all_ok():
    ptask1 = create_task(ok())
    ptask2 = create_task(ok())
    stask1 = create_task(ok())
    stask2 = create_task(ok())

    await gather_graceful([ptask1, ptask2], secondary=[stask1, stask2])
    assert ptask1.done() and await ptask1
    assert ptask2.done() and await ptask2
    assert stask1.done() and await stask1
    assert stask2.done() and await stask2


async def test_gather_primary_ok():
    ptask1 = create_task(ok())
    ptask2 = create_task(ok())

    await gather_graceful([ptask1, ptask2])
    assert ptask1.done() and await ptask1
    assert ptask2.done() and await ptask2


async def test_gather_secondary_ok():
    stask1 = create_task(ok())
    stask2 = create_task(ok())

    await gather_graceful(secondary=[stask1, stask2])
    assert stask1.done() and await stask1
    assert stask2.done() and await stask2


async def test_gather_primary_failed_no_wait():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(ValueError):
        await gather_graceful([ptask1, ptask2], secondary=[stask])

    assert ptask1.exception()
    assert not stask.done() and not ptask2.done()
    await sleep(0.01)
    assert stask.cancelled() and ptask2.cancelled()


async def test_gather_primary_failed_wait_cancelled():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(ValueError):
        await gather_graceful(
            [ptask1, ptask2], secondary=[stask],
            wait_cancelled=True,
        )

    assert ptask1.exception()
    assert stask.cancelled() and ptask2.cancelled()


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_gather_secondary_failed(wait_cancelled):
    ptask = create_task(ok(0.01))
    stask1 = create_task(fail())
    stask2 = create_task(ok(0.01))

    await gather_graceful(
        [ptask], secondary=[stask1, stask2],
        wait_cancelled=wait_cancelled,
    )
    assert ptask.done()
    assert stask1.exception()
    assert stask2.done() and not stask2.cancelled()


async def test_gather_primary_cancelled_no_wait():
    ptask1 = create_task(cancel())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(CancelledError):
        await gather_graceful([ptask1, ptask2], secondary=[stask])

    assert ptask1.cancelled()
    assert not stask.done() and not ptask2.done()
    await sleep(0.01)
    assert stask.cancelled() and ptask2.cancelled()


async def test_gather_primary_cancelled_wait_cancelled():
    async def cancel():
        raise CancelledError

    async def ok():
        await sleep(100)

    ptask1 = create_task(cancel())
    ptask2 = create_task(ok())
    stask = create_task(ok())

    with pytest.raises(CancelledError):
        await gather_graceful(
            [ptask1, ptask2], secondary=[stask],
            wait_cancelled=True,
        )

    assert ptask1.cancelled()
    assert ptask2.cancelled()
    assert stask.cancelled()


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_gather_secondary_cancelled(wait_cancelled):
    ptask = create_task(ok(0.01))
    stask1 = create_task(cancel())
    stask2 = create_task(ok(0.01))

    await gather_graceful(
        [ptask], secondary=[stask1, stask2],
        wait_cancelled=wait_cancelled,
    )
    assert ptask.done()
    assert stask1.cancelled()
    assert stask2.done() and not stask2.cancelled()


async def test_gather_external_cancel_no_wait():
    ptask = create_task(ok(100))
    stask = create_task(ok(100))
    task = create_task(gather_graceful([ptask], secondary=[stask]))

    await sleep(0.01)
    assert not ptask.done() and not stask.done()

    task.cancel()
    await sleep(0.01)
    assert ptask.cancelled() and stask.cancelled()
    with pytest.raises(CancelledError):
        await task


async def test_gather_external_cancel_wait_cancelled():
    async def cancel():
        with suppress(CancelledError):
            await sleep(100)
        await sleep(0.01)

    ptask = create_task(cancel())
    stask = create_task(cancel())
    task = create_task(gather_graceful([ptask], secondary=[stask]))

    await sleep(0.01)
    assert not ptask.done() and not stask.done()

    task.cancel()
    await sleep(0.005)
    assert not ptask.done() and not stask.done()
    await sleep(0.01)
    assert ptask.done() and stask.done()
    with pytest.raises(CancelledError):
        await task
