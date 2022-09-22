from asyncio import CancelledError, create_task, sleep
from contextlib import suppress

import pytest

from aiomisc import wait_graceful
from tests.tests_gather.conftest import ok, fail, cancel


async def test_wait_all_ok():
    ptask1 = create_task(ok())
    ptask2 = create_task(ok())
    stask1 = create_task(ok())
    stask2 = create_task(ok())

    await wait_graceful([ptask1, ptask2], [stask1, stask2])
    assert ptask1.done() and await ptask1
    assert ptask2.done() and await ptask2
    assert stask1.done() and await stask1
    assert stask2.done() and await stask2


async def test_wait_primary_ok():
    ptask1 = create_task(ok())
    ptask2 = create_task(ok())

    await wait_graceful([ptask1, ptask2])
    assert ptask1.done() and await ptask1
    assert ptask2.done() and await ptask2


async def test_wait_secondary_ok():
    stask1 = create_task(ok())
    stask2 = create_task(ok())

    await wait_graceful(primary=[], secondary=[stask1, stask2])
    assert stask1.done() and await stask1
    assert stask2.done() and await stask2


async def test_wait_primary_failed_no_wait():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(ValueError):
        await wait_graceful([ptask1, ptask2], [stask])

    assert ptask1.exception()
    assert not stask.done() and not ptask2.done()
    await sleep(0.01)
    assert stask.cancelled() and ptask2.cancelled()


async def test_wait_primary_failed_wait_cancelled():
    ptask1 = create_task(fail())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(ValueError):
        await wait_graceful([ptask1, ptask2], [stask], wait_cancelled=True)

    assert ptask1.exception()
    assert stask.cancelled() and ptask2.cancelled()


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_wait_secondary_failed(wait_cancelled):
    ptask = create_task(ok(0.01))
    stask1 = create_task(fail())
    stask2 = create_task(ok(0.01))

    await wait_graceful(
        [ptask], [stask1, stask2],
        wait_cancelled=wait_cancelled,
    )
    assert ptask.done()
    assert stask1.exception()
    assert stask2.done() and not stask2.cancelled()


async def test_wait_primary_cancelled_no_wait():
    ptask1 = create_task(cancel())
    ptask2 = create_task(ok(100))
    stask = create_task(ok(100))

    with pytest.raises(CancelledError):
        await wait_graceful([ptask1, ptask2], [stask])

    assert ptask1.cancelled()
    assert not stask.done() and not ptask2.done()
    await sleep(0.01)
    assert stask.cancelled() and ptask2.cancelled()


async def test_wait_primary_cancelled_wait_cancelled():
    async def cancel():
        raise CancelledError

    async def ok():
        await sleep(100)

    ptask1 = create_task(cancel())
    ptask2 = create_task(ok())
    stask = create_task(ok())

    with pytest.raises(CancelledError):
        await wait_graceful([ptask1, ptask2], [stask], wait_cancelled=True)

    assert ptask1.cancelled()
    assert ptask2.cancelled()
    assert stask.cancelled()


@pytest.mark.parametrize("wait_cancelled", [False, True])
async def test_wait_secondary_cancelled(wait_cancelled):
    ptask = create_task(ok(0.01))
    stask1 = create_task(cancel())
    stask2 = create_task(ok(0.01))

    await wait_graceful(
        [ptask], [stask1, stask2],
        wait_cancelled=wait_cancelled,
    )
    assert ptask.done()
    assert stask1.cancelled()
    assert stask2.done() and not stask2.cancelled()


async def test_wait_external_cancel_no_wait():
    ptask = create_task(ok(100))
    stask = create_task(ok(100))
    task = create_task(wait_graceful([ptask], [stask]))

    await sleep(0.01)
    assert not ptask.done() and not stask.done()

    task.cancel()
    await sleep(0.01)
    assert ptask.cancelled() and stask.cancelled()
    with pytest.raises(CancelledError):
        await task


async def test_wait_external_cancel_wait_cancelled():
    async def cancel():
        with suppress(CancelledError):
            await sleep(100)
        await sleep(0.01)

    ptask = create_task(cancel())
    stask = create_task(cancel())
    task = create_task(wait_graceful([ptask], [stask]))

    await sleep(0.01)
    assert not ptask.done() and not stask.done()

    task.cancel()
    await sleep(0.005)
    assert not ptask.done() and not stask.done()
    await sleep(0.01)
    assert ptask.done() and stask.done()
    with pytest.raises(CancelledError):
        await task
