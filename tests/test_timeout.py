import asyncio

import pytest

import aiomisc

pytestmark = pytest.mark.catch_loop_exceptions


async def test_simple(event_loop):
    @aiomisc.timeout(0)
    async def test():
        await asyncio.sleep(0.05)

    with pytest.raises(asyncio.TimeoutError):
        await test()


async def test_already_done_2(event_loop):
    @aiomisc.timeout(0.5)
    async def test(sec):
        await asyncio.sleep(sec)

    task = event_loop.create_task(test(10))
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task


async def test_non_coroutine(event_loop):
    with pytest.raises(TypeError):

        @aiomisc.timeout(0)
        def test():
            return
