import asyncio
import time

import pytest
from async_timeout import timeout

from aiomisc.backoff import asyncbackoff


@pytest.mark.asyncio
async def test_simple(event_loop):
    mana = 0

    @asyncbackoff(0.10, 1)
    async def test():
        nonlocal mana

        if mana < 5:
            mana += 1
            await asyncio.sleep(0.05)
            raise ValueError("Not enough mana")

    await test()

    assert mana == 5


@pytest.mark.asyncio
async def test_simple_fail(event_loop):
    mana = 0

    @asyncbackoff(0.10, 0.5)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(0.05)
            raise ValueError("Not enough mana")

    with pytest.raises(ValueError):
        await test()

    assert mana


@pytest.mark.asyncio
async def test_too_long(event_loop):
    mana = 0

    @asyncbackoff(0.5, 0.5)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    with pytest.raises(asyncio.TimeoutError):
        await test()

    assert mana < 2


@pytest.mark.asyncio
async def test_too_long_multiple_times(event_loop):
    mana = 0
    deadline = 0.5
    waterline = 0.06

    @asyncbackoff(waterline, deadline)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    async with timeout(deadline + waterline):
        with pytest.raises(asyncio.TimeoutError):
            await test()

    assert mana < 11


@pytest.mark.asyncio
async def test_exit(event_loop):
    mana = 0

    @asyncbackoff(0.05, 0)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    with pytest.raises(asyncio.TimeoutError):
        await test()

    assert mana < 11


@pytest.mark.asyncio
async def test_pause(event_loop):
    mana = 0

    @asyncbackoff(0.05, 0.5, 0.35)
    async def test():
        nonlocal mana

        mana += 1
        await asyncio.sleep(0.2)

        raise ValueError("Not enough mana")

    with pytest.raises(asyncio.TimeoutError):
        await test()

    assert mana == 2


@pytest.mark.asyncio
async def test_no_waterline(event_loop):
    mana = 0

    @asyncbackoff(None, 1, 0)
    async def test():
        nonlocal mana

        mana += 1
        await asyncio.sleep(0.2)

        raise ValueError("RETRY")

    with pytest.raises(ValueError, match="^RETRY$"):
        await test()

    assert mana == 5


@pytest.mark.asyncio
@pytest.mark.parametrize('max_sleep', (0.5, 1))
async def test_no_deadline(event_loop, max_sleep):
    mana = 0

    @asyncbackoff(0.15, None, 0)
    async def test():
        nonlocal mana

        mana += 1
        await asyncio.sleep(max_sleep - (mana - 1) * 0.1)

    await test()

    assert mana == max_sleep * 10


def test_values(event_loop):
    with pytest.raises(ValueError):
        asyncbackoff(-1, 1)

    with pytest.raises(ValueError):
        asyncbackoff(0, -1)

    with pytest.raises(ValueError):
        asyncbackoff(0, 0, -0.1)

    with pytest.raises(TypeError):
        asyncbackoff(0, 0)(lambda x: None)


@pytest.mark.asyncio
async def test_too_long_multiple(event_loop):
    mana = 0

    @asyncbackoff(0.5, 0.5)
    async def test():
        nonlocal mana

        if mana < 500:
            mana += 1
            await asyncio.sleep(5)
            raise ValueError("Not enough mana")

    t = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t2 = time.monotonic() - t
    assert t2 > 0.5
    with pytest.raises(asyncio.TimeoutError):
        await test()

    t3 = time.monotonic() - t
    assert t3 > 1

    assert mana < 4
