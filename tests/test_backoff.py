import asyncio
import time

import pytest
from async_timeout import timeout

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_kwargs(loop):
    mana = 0

    @aiomisc.asyncbackoff(
        attempt_timeout=0.5,
        deadline=0.5,
        pause=0,
        exceptions=(Exception,),
    )
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    t = time.time()
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t2 = time.time() - t
    assert t2 > 0.4
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t3 = time.time() - t
    assert t3 > 0.8

    assert mana < 3.8


async def test_simple(loop):
    mana = 0

    @aiomisc.asyncbackoff(0.10, 1, None, Exception)
    async def test():
        nonlocal mana

        if mana < 5:
            mana += 1
            await asyncio.sleep(0.05)
            raise ValueError("Not enough mana")

    await test()

    assert mana == 5


async def test_simple_fail(loop):
    mana = 0

    @aiomisc.asyncbackoff(0.10, 0.5)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(0.05)
            raise ValueError("Not enough mana")

    with pytest.raises(ValueError):
        await test()

    assert mana


async def test_too_long(loop):
    mana = 0

    @aiomisc.asyncbackoff(0.5, 0.5, 0, Exception)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    with pytest.raises(asyncio.TimeoutError):
        await test()

    assert mana < 2


async def test_too_long_multiple_times(loop):
    mana = 0
    deadline = 0.5
    attempt_time = 0.06

    @aiomisc.asyncbackoff(attempt_time, deadline, 0, Exception)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    async with timeout(2):
        with pytest.raises(asyncio.TimeoutError):
            await test()

    assert mana < 11


async def test_exit(loop):
    mana = 0

    @aiomisc.asyncbackoff(0.05, 0)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    with pytest.raises(asyncio.TimeoutError):
        await test()

    assert mana < 11


async def test_pause(loop):
    mana = 0
    condition = asyncio.Condition()

    @aiomisc.asyncbackoff(0.05, 1.2, 0.35)
    async def test():
        nonlocal mana

        async with condition:
            mana += 1
            condition.notify_all()

        await asyncio.sleep(0.2)
        raise ValueError("Not enough mana")

    task = loop.create_task(test())

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: mana == 2),
            timeout=5,
        )

    with pytest.raises(asyncio.TimeoutError):
        await task


async def test_no_waterline(loop):
    mana = 0
    condition = asyncio.Condition()

    @aiomisc.asyncbackoff(None, 1, 0, Exception)
    async def test():
        nonlocal mana

        async with condition:
            mana += 1
            await asyncio.sleep(0.1)
            condition.notify_all()
            raise ValueError("RETRY")

    task = loop.create_task(test())

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: mana >= 5),
            timeout=2,
        )

    with pytest.raises(ValueError, match="^RETRY$"):
        await task


@pytest.mark.parametrize("max_sleep", (0.5, 1))
async def test_no_deadline(loop, max_sleep):
    mana = 0
    condition = asyncio.Condition()

    @aiomisc.asyncbackoff(0.15, None, 0, Exception)
    async def test():
        nonlocal mana

        mana += 1
        await asyncio.sleep(max_sleep - (mana - 1) * 0.1)

        async with condition:
            condition.notify_all()

    task = loop.create_task(test())

    async with condition:
        await asyncio.wait_for(
            condition.wait_for(lambda: mana == max_sleep * 10),
            timeout=max_sleep * 10,
        )

    await asyncio.wait_for(task, timeout=max_sleep)


def test_values(loop):
    with pytest.raises(ValueError):
        aiomisc.asyncbackoff(-1, 1)

    with pytest.raises(ValueError):
        aiomisc.asyncbackoff(0, -1)

    with pytest.raises(ValueError):
        aiomisc.asyncbackoff(0, 0, -0.1)

    with pytest.raises(TypeError):
        aiomisc.asyncbackoff(0, 0)(lambda x: None)


async def test_too_long_multiple(loop):
    mana = 0

    @aiomisc.asyncbackoff(0.5, 0.5, 0, Exception)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    t = time.time()
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t2 = time.time() - t
    assert t2 > 0.4
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t3 = time.time() - t
    assert t3 > 0.8

    assert mana < 3.8


@pytest.mark.parametrize("max_tries", (1, 2, 5))
async def test_max_tries(loop, max_tries):
    mana = 0

    @aiomisc.asyncbackoff(0.5, 0.5, 0, Exception, max_tries=max_tries)
    async def test():
        nonlocal mana
        mana += 1
        raise ValueError("RETRY")

    with pytest.raises(ValueError, match="^RETRY$"):
        await test()

    assert mana == max_tries


@pytest.mark.parametrize("max_mana", (1, 2, 5))
async def test_giveup(loop, max_mana):
    mana = 0
    giveup_exception = None

    def giveup(exception):
        nonlocal giveup_exception
        giveup_exception = exception
        return mana >= max_mana

    @aiomisc.asyncbackoff(0.5, 0.5, 0, Exception, giveup=giveup)
    async def test():
        nonlocal mana
        mana += 1
        raise ValueError("RETRY")

    with pytest.raises(ValueError, match="^RETRY$") as e:
        await test()

    assert giveup_exception is e.value
    assert mana == max_mana


async def test_last_exception_is_last(loop):
    mana = 0

    class TestExc(Exception):
        pass

    @aiomisc.asyncbackoff(1, 2, 0)
    async def test():
        nonlocal mana

        if mana == 0:
            mana += 1
            await asyncio.sleep(1.5)  # causes TimeoutError on first try

        raise TestExc  # this is last exception actually

    with pytest.raises(TestExc):
        await test()


async def test_asyncbackoff_retry(loop):
    mana = 0

    @aiomisc.asyncbackoff(None, None, 0, Exception, max_tries=5)
    async def test():
        nonlocal mana
        mana += 1
        raise ValueError("RETRY")

    with pytest.raises(ValueError, match="^RETRY$"):
        await test()

    assert mana == 5


async def test_asyncretry(loop):
    mana = 0

    @aiomisc.asyncretry(5)
    async def test():
        nonlocal mana
        mana += 1
        raise ValueError("RETRY")

    with pytest.raises(ValueError, match="^RETRY$"):
        await test()

    assert mana == 5
