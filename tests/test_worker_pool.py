import asyncio
import operator
import platform
import sys
import threading
from multiprocessing.context import ProcessError
from os import getpid
from time import sleep

import pytest
from setproctitle import setproctitle

from aiomisc import WorkerPool


skipif = pytest.mark.skipif(
    sys.version_info < (3, 7),
    reason="https://bugs.python.org/issue37380",
)


@pytest.fixture
async def worker_pool(request, loop) -> WorkerPool:
    async with WorkerPool(
        4,
        initializer=setproctitle,
        initializer_args=(f"[WorkerPool] {request.node.name}",),
    ) as pool:
        yield pool


@skipif
async def test_success(worker_pool):
    results = await asyncio.gather(
        *[
            worker_pool.create_task(operator.mul, i, i)
            for i in range(worker_pool.workers * 2)
        ]
    )

    results = sorted(results)

    assert sorted(results) == [i * i for i in range(worker_pool.workers * 2)]


@skipif
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
                    worker_pool.create_task(sleep, 3600)
                    for _ in range(worker_pool.workers)
                ]
            ), timeout=1,
        )

    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )


@pytest.mark.skipif(
    platform.system() == "Windows", reason="Flapping on windows",
)
@skipif
async def test_incomplete_task_pool_reuse(worker_pool):
    pids_start = set(process.pid for process in worker_pool.processes)

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
                    worker_pool.create_task(sleep, 3600)
                    for _ in range(worker_pool.workers)
                ]
            ), timeout=1,
        )

    await asyncio.gather(
        *[
            worker_pool.create_task(getpid)
            for _ in range(worker_pool.workers * 4)
        ]
    )

    pids_end = set(process.pid for process in worker_pool.processes)

    assert list(pids_start) == list(pids_end)


@skipif
async def test_exceptions(worker_pool):
    results = await asyncio.gather(
        *[
            worker_pool.create_task(operator.truediv, i, 0)
            for i in range(worker_pool.workers * 2)
        ], return_exceptions=True
    )

    assert len(results) == worker_pool.workers * 2

    for exc in results:
        assert isinstance(exc, ZeroDivisionError)


@skipif
async def test_exit(worker_pool):
    exceptions = await asyncio.wait_for(
        asyncio.gather(
            *[
                worker_pool.create_task(exit, 1)
                for _ in range(worker_pool.workers)
            ],
            return_exceptions=True
        ), timeout=5,
    )

    assert len(exceptions) == worker_pool.workers
    for exc in exceptions:
        assert isinstance(exc, ProcessError)


@skipif
async def test_exit_respawn(worker_pool):
    exceptions = await asyncio.wait_for(
        asyncio.gather(
            *[
                worker_pool.create_task(exit, 1)
                for _ in range(worker_pool.workers * 3)
            ],
            return_exceptions=True
        ), timeout=5,
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


def get_initializer_args():
    return INITIALIZER_ARGS, INITIALIZER_KWARGS


@skipif
async def test_initializer(worker_pool):
    pool = WorkerPool(
        1, initializer=initializer, initializer_args=("foo",),
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


@skipif
async def test_bad_initializer(worker_pool):
    pool = WorkerPool(1, initializer=bad_initializer)

    with pytest.raises(ZeroDivisionError):
        async with pool:
            await pool.create_task(get_initializer_args)


@skipif
async def test_threads_active_count_in_pool(worker_pool):
    threads = await worker_pool.create_task(threading.active_count)
    assert threads == 1
