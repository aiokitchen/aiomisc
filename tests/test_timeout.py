import asyncio
import pytest

from aiomisc.timeout import timeout


@pytest.mark.asyncio
async def test_simple(event_loop):
    @timeout(0)
    async def test():
        await asyncio.sleep(0.05)

    with pytest.raises(asyncio.TimeoutError):
        await test()


@pytest.mark.asyncio
async def test_already_done(event_loop):
    @timeout(0)
    async def test():
        return

    await test()


@pytest.mark.asyncio
async def test_already_done(event_loop):
    @timeout(0.5)
    async def test(sec):
        await asyncio.sleep(sec)

    task = event_loop.create_task(test(10))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_non_coroutine(event_loop):
    with pytest.raises(TypeError):
        @timeout(0)
        def test():
            return
