import asyncio
from multiprocessing.context import ProcessError
from os import getpid

import pytest

from aiomisc.worker_pool import WorkerPool


@pytest.fixture
async def worker_pool(loop) -> WorkerPool:
    async with WorkerPool(4) as pool:
        yield pool


async def test_simple(worker_pool):
    pids = set(await asyncio.gather(
        *[worker_pool.create_task(getpid)
          for _ in range(worker_pool.workers * 4)]
    ))

    assert len(pids) == worker_pool.workers


async def test_exit(worker_pool):
    exceptions = await asyncio.gather(
        *[worker_pool.create_task(exit, 1)
          for _ in range(worker_pool.workers)],
        return_exceptions=True
    )

    assert len(exceptions) == worker_pool.workers
    for exc in exceptions:
        assert isinstance(exc, ProcessError)


async def test_exit_respawn(worker_pool):
    exceptions = await asyncio.gather(
        *[worker_pool.create_task(exit, 1)
          for _ in range(worker_pool.workers * 3)],
        return_exceptions=True
    )

    assert len(exceptions) == worker_pool.workers * 3
    for exc in exceptions:
        assert isinstance(exc, ProcessError)
