import asyncio
import concurrent.futures
from contextlib import contextmanager, suppress

import pytest
import time

import uvloop

from aiomisc.thread_pool import ThreadPoolExecutor


@pytest.fixture
def timer():
    @contextmanager
    def timer(expected_time=0, *, dispersion=0.5):
        expected_time = float(expected_time)
        dispersion_value = expected_time * dispersion

        now = time.monotonic()

        yield

        delta = time.monotonic() - now

        lower_bound = expected_time - dispersion_value
        upper_bound = expected_time + dispersion_value

        assert lower_bound < delta < upper_bound

    return timer


thread_pool_implementation = (
    lambda loop: ThreadPoolExecutor(4, loop=loop),
    lambda loop: concurrent.futures.ThreadPoolExecutor(4)
)


thread_pool_ids = (
    'aiomisc pool',
    'default pool',
)


@pytest.fixture(params=thread_pool_implementation, ids=thread_pool_ids)
def thread_pool_executor(request):
    yield request.param


policies = (
    uvloop.EventLoopPolicy(),
    asyncio.DefaultEventLoopPolicy(),
)

policy_ids = (
    'uvloop',
    'asyncio',
)


@pytest.fixture(params=policies, ids=policy_ids, autouse=True)
def event_loop(request, thread_pool_executor):
    with suppress(Exception):
        asyncio.get_event_loop().close()

    asyncio.set_event_loop_policy(request.param)

    loop = asyncio.new_event_loop()
    pool = thread_pool_executor(loop)
    loop.set_default_executor(pool)
    asyncio.set_event_loop(loop)

    try:
        yield loop
    finally:
        pool.shutdown(wait=True)
        loop.close()
