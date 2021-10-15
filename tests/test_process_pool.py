import asyncio
import os
import signal
from time import sleep, time

import pytest
from async_timeout import timeout

from aiomisc.process_pool import ProcessPoolExecutor


@pytest.fixture
def pool():
    pool = ProcessPoolExecutor(4)
    try:
        yield pool
    finally:
        pool.shutdown(True)


async def test_simple(pool, loop, timer):
    current_time = await loop.run_in_executor(pool, time)
    assert current_time > 0

    async with timeout(2):
        with timer(1):
            await asyncio.gather(
                *[
                    loop.run_in_executor(pool, sleep, 1) for _ in range(4)
                ]
            )


async def test_exception(pool, loop):
    with pytest.raises(ZeroDivisionError):
        await loop.run_in_executor(pool, divmod, 1, 0)


def suicide():
    os.kill(os.getpid(), signal.SIGINT)


async def test_exit(pool, loop):
    async with timeout(2):
        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(
                *[loop.run_in_executor(pool, suicide) for _ in range(4)]
            )
