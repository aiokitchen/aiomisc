import asyncio
import operator
import sys
from multiprocessing.context import ProcessError
from os import getpid
from time import sleep

import pytest

from aiomisc import WorkerPool


@pytest.fixture
async def worker_pool(loop) -> WorkerPool:
    async with WorkerPool(4) as pool:
        yield pool


async def test_success(worker_pool):
    results = await asyncio.gather(*[
        worker_pool.create_task(operator.mul, i, i)
        for i in range(worker_pool.workers * 2)
    ])

    results = sorted(results)

    assert results == [i * i for i in range(worker_pool.workers * 2)]


async def test_incomplete_task_kill(worker_pool):
    pids_start = set(await asyncio.gather(
        *[worker_pool.create_task(getpid)
          for _ in range(worker_pool.workers * 4)]
    ))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(*[
                worker_pool.create_task(sleep, 3600)
                for _ in range(worker_pool.workers)
            ]), timeout=1
        )

    pids_end = set(await asyncio.gather(
        *[worker_pool.create_task(getpid)
          for _ in range(worker_pool.workers * 4)]
    ))

    assert list(pids_start) != list(pids_end)


async def test_exceptions(worker_pool):
    results = await asyncio.gather(*[
        worker_pool.create_task(operator.truediv, i, 0)
        for i in range(worker_pool.workers * 2)
    ], return_exceptions=True)

    assert len(results) == worker_pool.workers * 2

    for exc in results:
        assert isinstance(exc, ZeroDivisionError)


async def test_exit(worker_pool):
    exceptions = await asyncio.gather(
        *[worker_pool.create_task(exit, 1)
          for _ in range(worker_pool.workers)],
        return_exceptions=True
    )

    assert len(exceptions) == worker_pool.workers
    for exc in exceptions:
        assert isinstance(exc, ProcessError)


@pytest.mark.skipif(sys.version_info < (3, 7), reason="bpo37380")
async def test_exit_respawn(worker_pool):
    exceptions = await asyncio.gather(
        *[worker_pool.create_task(exit, 1)
          for _ in range(worker_pool.workers * 3)],
        return_exceptions=True
    )

    assert len(exceptions) == worker_pool.workers * 3
    for exc in exceptions:
        assert isinstance(exc, ProcessError)
