import asyncio
from contextlib import contextmanager

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


@pytest.fixture()
def event_loop():
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    asyncio.get_event_loop().close()

    loop = asyncio.new_event_loop()
    thread_pool = ThreadPoolExecutor(4, loop=loop)

    loop.set_default_executor(thread_pool)

    asyncio.set_event_loop(loop)

    try:
        yield loop
    finally:
        thread_pool.shutdown()
        loop.close()
