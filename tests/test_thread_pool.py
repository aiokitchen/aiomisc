import asyncio
import os
from contextlib import suppress

import pytest
import time

from async_timeout import timeout

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


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


async def test_future_already_done(executor: aiomisc.ThreadPoolExecutor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    for future in futures:
        future.set_exception(asyncio.CancelledError())

    await asyncio.gather(*futures, return_exceptions=True)


async def test_future_when_pool_shutting_down(executor):
    futures = []

    for _ in range(10):
        futures.append(executor.submit(time.sleep, 0.1))

    executor.shutdown(wait=False)

    done, _ = await asyncio.wait(futures)

    for task in done:
        with pytest.raises(RuntimeError):
            task.result()


async def test_failed_future_already_done(executor):
    futures = []

    def exc():
        time.sleep(0.1)
        raise Exception

    for _ in range(10):
        futures.append(executor.submit(exc))

    for future in futures:
        future.set_exception(asyncio.CancelledError())

    await asyncio.gather(*futures, return_exceptions=True)


async def test_cancel(executor: aiomisc.ThreadPoolExecutor, loop, timer):
    assert executor

    sleep = aiomisc.threaded(time.sleep)

    with timer(1, dispersion=2):
        tasks = [loop.create_task(sleep(1)) for _ in range(1000)]

        await asyncio.sleep(1)

        for task in tasks:
            task.cancel()

        executor.shutdown(wait=True)


async def test_simple(loop, timer):
    sleep = aiomisc.threaded(time.sleep)

    with timer(1):
        await asyncio.gather(
            sleep(1),
            sleep(1),
            sleep(1),
            sleep(1),
        )


async def test_threaded_generator(loop, timer):
    @aiomisc.threaded
    def arange(*args):
        return (yield from range(*args))

    async with timeout(2):
        count = 10

        result = []
        agen = arange(count)
        async for item in agen:
            result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_max_size(loop, timer):
    @aiomisc.threaded_iterable(max_size=1)
    def arange(*args):
        return (yield from range(*args))

    async with timeout(2):
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


async def test_threaded_generator_exception(loop, timer):
    @aiomisc.threaded_iterable
    def arange(*args):
        yield from range(*args)
        raise ZeroDivisionError

    async with timeout(2):
        count = 10

        result = []
        agen = arange(count)

        with pytest.raises(ZeroDivisionError):
            async for item in agen:
                result.append(item)

        assert result == list(range(count))


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

    async with timeout(2):
        counter = 0

        async with noise() as gen:
            async for _ in gen:     # NOQA
                counter += 1
                if counter > 9:
                    break

        wait_counter = 0
        while not stopped and wait_counter < 5:
            await asyncio.sleep(1)
            wait_counter += 1

        assert stopped


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

    async with timeout(2):
        async with noise() as gen:
            counter = 0
            async for _ in gen:     # NOQA
                counter += 1
                if counter > 9:
                    break

        assert stopped


async def test_threaded_generator_non_generator_raises(loop, timer):
    @aiomisc.threaded_iterable()
    def errored():
        raise RuntimeError("Aaaaaaaa")

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored():       # NOQA
                pass


async def test_threaded_generator_func_raises(loop, timer):
    @aiomisc.threaded
    def errored(val):
        if val:
            raise RuntimeError("Aaaaaaaa")

        yield

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored(True):    # NOQA
                pass
