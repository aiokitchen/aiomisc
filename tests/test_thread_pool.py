import asyncio
from contextlib import suppress
from functools import partial

import pytest
import time

from aiomisc.thread_pool import ThreadPoolExecutor, run_in_executor, threaded


@pytest.fixture
def executor(event_loop: asyncio.AbstractEventLoop):
    thread_pool = ThreadPoolExecutor(8, loop=event_loop)
    event_loop.set_default_executor(thread_pool)
    try:
        yield thread_pool
    finally:
        with suppress(Exception):
            thread_pool.shutdown(wait=True)

        event_loop.set_default_executor(None)


@pytest.mark.asyncio
async def test_threaded(executor: ThreadPoolExecutor, timer):
    assert executor

    sleep = threaded(time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )


@pytest.mark.asyncio
async def test_run_in_executor(executor: ThreadPoolExecutor, timer):
    assert executor

    sleep = partial(run_in_executor, time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )


@pytest.mark.asyncio
async def test_threaded_exc(executor: ThreadPoolExecutor):
    assert executor

    @threaded
    def worker():
        raise Exception

    number = 90

    done, _ = await asyncio.wait([worker() for _ in range(number)])

    for task in done:
        with pytest.raises(Exception):
            task.result()


@pytest.mark.asyncio
async def test_future_already_done(executor: ThreadPoolExecutor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    for future in futures:
        future.set_exception(asyncio.CancelledError())

    await asyncio.wait(futures)


@pytest.mark.asyncio
async def test_future_when_pool_shutting_down(executor: ThreadPoolExecutor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    executor.shutdown(wait=False)

    done, _ = await asyncio.wait(futures)

    for task in done:
        with pytest.raises(RuntimeError):
            task.result()


@pytest.mark.asyncio
async def test_failed_future_already_done(executor: ThreadPoolExecutor):
    futures = []

    def exc():
        time.sleep(0.1)
        raise Exception

    for _ in range(10):
        futures.append(executor.submit(exc))

    for future in futures:
        future.set_exception(asyncio.CancelledError())

    await asyncio.wait(futures)


@pytest.mark.asyncio
async def test_cancel(executor: ThreadPoolExecutor, event_loop, timer):
    assert executor

    sleep = threaded(time.sleep)

    with timer(1, dispersion=2):
        tasks = [event_loop.create_task(sleep(1)) for _ in range(1000)]

        await asyncio.sleep(1)

        for task in tasks:
            task.cancel()

        executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_simple(event_loop, timer):
    sleep = threaded(time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )
