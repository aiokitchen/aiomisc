import asyncio
import os
from contextlib import suppress

import pytest
import time

import aiomisc


@pytest.fixture
def executor(loop: asyncio.AbstractEventLoop):
    thread_pool = aiomisc.ThreadPoolExecutor(8, loop=loop)
    loop.set_default_executor(thread_pool)
    try:
        yield thread_pool
    finally:
        with suppress(Exception):
            thread_pool.shutdown(wait=True)

        loop.set_default_executor(None)


@pytest.mark.asyncio
async def test_threaded(executor: aiomisc.ThreadPoolExecutor, timer):
    assert executor

    sleep = aiomisc.threaded(time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )


@pytest.mark.asyncio
async def test_threaded_exc(executor: aiomisc.ThreadPoolExecutor):
    assert executor

    @aiomisc.threaded
    def worker():
        raise Exception

    number = 90

    done, _ = await asyncio.wait([worker() for _ in range(number)])

    for task in done:
        with pytest.raises(Exception):
            task.result()


@pytest.mark.asyncio
async def test_future_already_done(executor: aiomisc.ThreadPoolExecutor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    for future in futures:
        future.set_exception(asyncio.CancelledError())

    await asyncio.wait(futures)


@pytest.mark.asyncio
async def test_future_when_pool_shutting_down(executor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    executor.shutdown(wait=False)

    done, _ = await asyncio.wait(futures)

    for task in done:
        with pytest.raises(RuntimeError):
            task.result()


@pytest.mark.asyncio
async def test_failed_future_already_done(executor):
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
async def test_cancel(executor: aiomisc.ThreadPoolExecutor, loop, timer):
    assert executor

    sleep = aiomisc.threaded(time.sleep)

    with timer(1, dispersion=2):
        tasks = [loop.create_task(sleep(1)) for _ in range(1000)]

        await asyncio.sleep(1)

        for task in tasks:
            task.cancel()

        executor.shutdown(wait=True)


@pytest.mark.asyncio
async def test_simple(loop, timer):
    sleep = aiomisc.threaded(time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )


@pytest.mark.asyncio
async def test_threaded_generator(loop, timer):
    @aiomisc.threaded
    def arange(*args):
        return (yield from range(*args))

    count = 10

    result = []
    agen = arange(count)
    async for item in agen:
        result.append(item)

    assert result == list(range(count))


@pytest.mark.asyncio
async def test_threaded_generator_max_size(loop, timer):
    @aiomisc.threaded_iterable(max_size=1)
    def arange(*args):
        return (yield from range(*args))

    arange2 = aiomisc.threaded_iterable(max_size=1)(range)

    count = 10

    result = []
    agen = arange(count)
    async for item in agen:
        result.append(item)

    assert result == list(range(count))

    result = []
    agen = arange2(count)
    async for item in agen:
        result.append(item)

    assert result == list(range(count))


@pytest.mark.asyncio
async def test_threaded_generator_exception(loop, timer):
    @aiomisc.threaded_iterable
    def arange(*args):
        yield from range(*args)
        raise ZeroDivisionError

    count = 10

    result = []
    agen = arange(count)

    with pytest.raises(ZeroDivisionError):
        async for item in agen:
            result.append(item)

    assert result == list(range(count))


@pytest.mark.asyncio
async def test_threaded_generator_close(loop, timer):
    stopped = False

    @aiomisc.threaded_iterable(max_size=2)
    def noise():
        nonlocal stopped

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped = True

    gen = noise()
    counter = 0

    async for _ in gen:     # NOQA
        counter += 1
        if counter > 9:
            break

    await gen.close()
    assert stopped


@pytest.mark.asyncio
async def test_threaded_generator_close_cm(loop, timer):
    stopped = False

    @aiomisc.threaded_iterable(max_size=1)
    def noise():
        nonlocal stopped

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped = True

    async with noise() as gen:
        counter = 0
        async for _ in gen:     # NOQA
            counter += 1
            if counter > 9:
                break

    assert stopped
