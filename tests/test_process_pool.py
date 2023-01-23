import asyncio
import os
import signal
from time import sleep, time

import pytest

import aiomisc
from aiomisc.process_pool import ProcessPoolExecutor


@pytest.fixture
def pool():
    pool = ProcessPoolExecutor(4)
    try:
        yield pool
    finally:
        pool.shutdown(True)


@aiomisc.timeout(10)
async def test_simple(pool, loop, timer):
    current_time = await loop.run_in_executor(pool, time)
    assert current_time > 0

    with timer(1):
        await asyncio.wait_for(
            asyncio.gather(
                *[
                    loop.run_in_executor(pool, sleep, 1) for _ in range(4)
                ],
            ), timeout=2,
        )


@aiomisc.timeout(10)
async def test_exception(pool, loop):
    with pytest.raises(ZeroDivisionError):
        await loop.run_in_executor(pool, divmod, 1, 0)


def suicide():
    os.kill(os.getpid(), signal.SIGINT)


@pytest.mark.skip(reason="Stuck tests in GH actions")
@aiomisc.timeout(10)
async def test_exit(pool, loop):
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(
                *[loop.run_in_executor(pool, suicide) for _ in range(4)],
            ), timeout=2,
        )
