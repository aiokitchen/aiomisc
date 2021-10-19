import asyncio
import gc
import os
import threading
import time
import weakref
from contextlib import suppress

import pytest
from async_timeout import timeout

import aiomisc
from aiomisc.iterator_wrapper import ChannelClosed, FromThreadChannel


try:
    import contextvars
except ImportError:
    contextvars = None


pytestmark = pytest.mark.catch_loop_exceptions


@pytest.fixture(params=(aiomisc.threaded, aiomisc.threaded_separate))
def threaded_decorator(request, executor: aiomisc.ThreadPoolExecutor):
    assert executor
    return request.param


@pytest.fixture
def executor(loop: asyncio.AbstractEventLoop):
    thread_pool = aiomisc.ThreadPoolExecutor(8)
    loop.set_default_executor(thread_pool)
    try:
        yield thread_pool
    finally:
        with suppress(Exception):
            thread_pool.shutdown(wait=True)

        thread_pool.shutdown(wait=True)


async def test_from_thread_channel(loop, threaded_decorator):
    channel = FromThreadChannel(maxsize=2, loop=loop)

    @threaded_decorator
    def in_thread():
        with channel:
            for i in range(10):
                channel.put(i)

    in_thread()
    result = []
    with pytest.raises(ChannelClosed):
        while True:
            result.append(await asyncio.wait_for(channel.get(), timeout=5))

    assert result == list(range(10))


async def test_from_thread_channel_wait_before(loop, threaded_decorator):
    channel = FromThreadChannel(maxsize=1, loop=loop)

    @threaded_decorator
    def in_thread():
        with channel:
            for i in range(10):
                channel.put(i)

    loop.call_later(0.1, in_thread)

    result = []
    with pytest.raises(ChannelClosed):
        while True:
            result.append(await asyncio.wait_for(channel.get(), timeout=5))

    assert result == list(range(10))


async def test_from_thread_channel_close(loop):
    channel = FromThreadChannel(maxsize=1, loop=loop)
    with channel:
        channel.put(1)

    with pytest.raises(ChannelClosed):
        channel.put(2)

    channel = FromThreadChannel(maxsize=1, loop=loop)
    task = loop.create_task(channel.get())

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=1)

    loop.call_soon(channel.put, 1)

    assert await channel.get() == 1


async def test_future_gc(thread_pool_executor, loop):
    thread_pool = thread_pool_executor(2)
    event = threading.Event()

    async def run():
        future = loop.create_future()

        cfuture = thread_pool.submit(time.sleep, 0.5)

        cfuture.add_done_callback(
            lambda *_: loop.call_soon_threadsafe(
                future.set_result, True,
            ),
        )

        weakref.finalize(cfuture, lambda *_: event.set())
        await future

    await run()

    gc.collect()
    event.wait(1)

    assert event.is_set()


async def test_threaded(threaded_decorator, timer):
    sleep = threaded_decorator(time.sleep)

    async with timeout(5):
        with timer(1):
            await asyncio.gather(
                sleep(1),
                sleep(1),
                sleep(1),
                sleep(1),
                sleep(1),
            )


async def test_threaded_exc(threaded_decorator):
    @threaded_decorator
    def worker():
        raise Exception

    async with timeout(1):
        number = 90

        done, _ = await asyncio.wait([worker() for _ in range(number)])

        for task in done:
            with pytest.raises(Exception):
                task.result()


async def test_future_already_done(executor: aiomisc.ThreadPoolExecutor):
    futures = []

    async with timeout(10):
        for _ in range(10):
            futures.append(executor.submit(time.sleep, 0.1))

        for future in futures:
            future.set_exception(asyncio.CancelledError())

        await asyncio.gather(*futures, return_exceptions=True)


async def test_future_when_pool_shutting_down(executor):
    futures = []

    async with timeout(10):
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

    async with timeout(10):
        for _ in range(10):
            futures.append(executor.submit(exc))

        for future in futures:
            future.set_exception(asyncio.CancelledError())

        await asyncio.gather(*futures, return_exceptions=True)


async def test_cancel(executor, loop, timer):
    sleep = aiomisc.threaded(time.sleep)

    async with timeout(2):
        with timer(1, dispersion=2):
            tasks = [asyncio.ensure_future(sleep(1)) for _ in range(1000)]

            await asyncio.sleep(1)

            for task in tasks:
                task.cancel()

    executor.shutdown(wait=True)


async def test_simple(threaded_decorator, loop, timer):
    sleep = threaded_decorator(time.sleep)

    async with timeout(2):
        with timer(1):
            await asyncio.gather(
                sleep(1),
                sleep(1),
                sleep(1),
                sleep(1),
            )


gen_decos = (
    aiomisc.threaded_iterable,
    aiomisc.threaded_iterable_separate,
)


@pytest.fixture(params=gen_decos)
def iterator_decorator(request):
    return request.param


async def test_threaded_generator(loop, timer):
    @aiomisc.threaded
    def arange(*args):
        return (yield from range(*args))

    async with timeout(10):
        count = 10

        result = []
        agen = arange(count)
        async for item in agen:
            result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_max_size(iterator_decorator, loop, timer):
    @iterator_decorator(max_size=1)
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


async def test_threaded_generator_exception(iterator_decorator, loop, timer):
    @iterator_decorator
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


async def test_threaded_generator_close(iterator_decorator, loop, timer):
    stopped = False

    @iterator_decorator(max_size=2)
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


async def test_threaded_generator_close_cm(iterator_decorator, loop, timer):
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def noise():
        nonlocal stopped

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped.set()

    async with timeout(2):
        async with noise() as gen:
            counter = 0
            async for _ in gen:     # NOQA
                counter += 1
                if counter > 9:
                    break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_close_break(iterator_decorator, loop, timer):
    stopped = threading.Event()

    @iterator_decorator(max_size=1)
    def noise():
        nonlocal stopped

        try:
            while True:
                yield os.urandom(32)
        finally:
            stopped.set()

    async with timeout(2):
        counter = 0
        async for _ in noise():     # NOQA
            counter += 1
            if counter > 9:
                break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_non_generator_raises(
        iterator_decorator, loop, timer,
):
    @iterator_decorator()
    def errored():
        raise RuntimeError("Aaaaaaaa")

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored():       # NOQA
                pass


async def test_threaded_generator_func_raises(iterator_decorator, loop, timer):
    @iterator_decorator
    def errored(val):
        if val:
            raise RuntimeError("Aaaaaaaa")

        yield

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored(True):    # NOQA
                pass


@pytest.mark.skipif(contextvars is None, reason="no contextvars support")
async def test_context_vars(threaded_decorator, loop):
    ctx_var = contextvars.ContextVar("test")

    @threaded_decorator
    def test(arg):
        value = ctx_var.get()
        assert value == arg * arg

    futures = []

    for i in range(8):
        ctx_var.set(i * i)
        futures.append(test(i))

    await asyncio.gather(*futures)


async def test_wait_coroutine_sync(threaded_decorator, loop):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1

    @threaded_decorator
    def test():
        aiomisc.sync_wait_coroutine(loop, coro)

    await test()
    assert result == 1


async def test_wait_coroutine_sync_exc(threaded_decorator, loop):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1
        raise RuntimeError("Test")

    @threaded_decorator
    def test():
        aiomisc.sync_wait_coroutine(loop, coro)

    with pytest.raises(RuntimeError):
        await test()

    assert result == 1
