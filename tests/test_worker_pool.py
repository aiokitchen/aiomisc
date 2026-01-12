import asyncio
import logging
import operator
import sys
import threading
from multiprocessing.context import ProcessError
from os import getpid
from time import sleep
from collections.abc import AsyncGenerator

import pytest
from setproctitle import setproctitle

import aiomisc
from aiomisc import WorkerPool
from aiomisc.worker_pool import WorkerPoolStatistic

PROCESS_NUM = 4


@pytest.fixture
async def worker_pool(
    request: pytest.FixtureRequest, event_loop: asyncio.AbstractEventLoop
) -> AsyncGenerator[WorkerPool, None]:
    async with WorkerPool(
        PROCESS_NUM,
        initializer=setproctitle,
        initializer_args=(f"[WorkerPool] {request.node.name}",),
        statistic_name=request.node.name,
    ) as pool:
        yield pool


@aiomisc.timeout(5)
async def test_success(worker_pool):
    results = await asyncio.gather(
        *[
            worker_pool.create_task(operator.mul, i, i)
            for i in range(worker_pool.workers * 2)
        ]
    )

    results = sorted(results)

    assert sorted(results) == [i * i for i in range(worker_pool.workers * 2)]


@aiomisc.timeout(5)
async def test_incomplete_task_kill(worker_pool):
    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(
                *[
                    worker_pool.create_task(sleep, 600)
                    for _ in range(worker_pool.workers)
                ]
            ),
            timeout=1,
        )

    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )


@pytest.mark.skipif(
    sys.platform in ("win32", "cygwin"), reason="Windows is ill"
)
@aiomisc.timeout(5)
async def test_incomplete_task_pool_reuse(request, worker_pool: WorkerPool):
    def get_stats() -> dict:
        stats = {}
        for metric in aiomisc.get_statistics(WorkerPoolStatistic):
            if metric.name == request.node.name:
                stats[metric.metric] = metric.value
        return stats

    stats = get_stats()
    while stats["spawning"] < PROCESS_NUM:
        await asyncio.sleep(0.1)
        stats = get_stats()

    pids_start = set(worker_pool.pids)

    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            asyncio.gather(
                *[
                    worker_pool.create_task(sleep, 600)
                    for _ in range(worker_pool.workers)
                ]
            ),
            timeout=1,
        )

    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )

    pids_end = set(worker_pool.pids)

    assert list(pids_start) == list(pids_end)


@aiomisc.timeout(5)
async def test_exceptions(worker_pool):
    results = await asyncio.gather(
        *[
            worker_pool.create_task(operator.truediv, i, 0)
            for i in range(worker_pool.workers * 2)
        ],
        return_exceptions=True,
    )

    assert len(results) == worker_pool.workers * 2

    for exc in results:
        assert isinstance(exc, ZeroDivisionError)


@aiomisc.timeout(5)
async def test_exit(worker_pool):
    exceptions = await asyncio.wait_for(
        asyncio.gather(
            *[
                worker_pool.create_task(exit, 1)
                for _ in range(worker_pool.workers)
            ],
            return_exceptions=True,
        ),
        timeout=5,
    )

    assert len(exceptions) == worker_pool.workers
    for exc in exceptions:
        assert isinstance(exc, ProcessError)


@aiomisc.timeout(30)
async def test_exit_respawn(worker_pool):
    exceptions = await asyncio.gather(
        *[
            worker_pool.create_task(exit, 1)
            for _ in range(worker_pool.workers * 3)
        ],
        return_exceptions=True,
    )
    assert len(exceptions) == worker_pool.workers * 3

    for exc in exceptions:
        assert isinstance(exc, ProcessError)


INITIALIZER_ARGS = None
INITIALIZER_KWARGS = None


def initializer(*args, **kwargs):
    global INITIALIZER_ARGS, INITIALIZER_KWARGS
    INITIALIZER_ARGS = args
    INITIALIZER_KWARGS = kwargs
    logging.info("Initializer done")


def get_initializer_args():
    return INITIALIZER_ARGS, INITIALIZER_KWARGS


@aiomisc.timeout(10)
async def test_initializer(worker_pool):
    pool = WorkerPool(
        1,
        initializer=initializer,
        initializer_args=("foo",),
        initializer_kwargs={"spam": "egg"},
    )
    async with pool:
        args, kwargs = await pool.create_task(get_initializer_args)

    assert args == ("foo",)
    assert kwargs == {"spam": "egg"}

    async with WorkerPool(1, initializer=initializer) as pool:
        args, kwargs = await pool.create_task(get_initializer_args)

    assert args == ()
    assert kwargs == {}

    async with WorkerPool(1) as pool:
        args, kwargs = await pool.create_task(get_initializer_args)

    assert args is None
    assert kwargs is None


def bad_initializer():
    return 1 / 0


@aiomisc.timeout(5)
async def test_bad_initializer(worker_pool):
    pool = WorkerPool(1, initializer=bad_initializer)

    with pytest.raises(ZeroDivisionError):
        async with pool:
            await pool.create_task(get_initializer_args)


@aiomisc.timeout(5)
async def test_threads_active_count_in_pool(worker_pool):
    threads = await worker_pool.create_task(threading.active_count)
    assert threads == 1
