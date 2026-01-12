import asyncio
import os
import signal
from time import sleep, time

import pytest

import aiomisc
from aiomisc.process_pool import ProcessPoolExecutor

POOL_SIZE = 4


@pytest.fixture
def pool():
    with ProcessPoolExecutor(POOL_SIZE) as pool:
        yield pool


@aiomisc.timeout(10)
async def test_simple(pool, event_loop, timer):
    current_time = await event_loop.run_in_executor(pool, time)
    assert current_time > 0

    with timer(1):
        await asyncio.wait_for(
            asyncio.gather(
                *[
                    event_loop.run_in_executor(pool, sleep, 1)
                    for _ in range(POOL_SIZE)
                ]
            ),
            timeout=2,
        )


@aiomisc.timeout(10)
async def test_exception(pool, event_loop):
    with pytest.raises(ZeroDivisionError):
        await event_loop.run_in_executor(pool, divmod, 1, 0)


def suicide():
    os.kill(os.getpid(), signal.SIGINT)


@aiomisc.timeout(10)
async def test_exit(pool, event_loop):
    await asyncio.wait_for(
        asyncio.gather(
            *[event_loop.run_in_executor(pool, suicide) for _ in range(4)],
            return_exceptions=True,
        ),
        timeout=2,
    )
