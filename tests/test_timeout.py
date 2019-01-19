import asyncio
import pytest

from aiomisc.timeout import timeout


@pytest.mark.asyncio
async def test_simple(loop):
    @timeout(0)
    async def test():
        await asyncio.sleep(0.05)

    with pytest.raises(asyncio.TimeoutError):
        await test()


@pytest.mark.asyncio
async def test_already_done(loop):
    @timeout(0)
    async def test():
        return

    await test()


@pytest.mark.asyncio
async def test_already_done_2(loop):
    @timeout(0.5)
    async def test(sec):
        await asyncio.sleep(sec)

    task = loop.create_task(test(10))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_non_coroutine(loop):
    with pytest.raises(TypeError):
        @timeout(0)
        def test():
            return
