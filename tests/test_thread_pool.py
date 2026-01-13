import asyncio
import concurrent.futures
import gc
import os
import threading
import time
import weakref
from contextlib import suppress

import pytest
from async_timeout import timeout

import aiomisc
from aiomisc import threaded, threaded_iterable
from aiomisc.iterator_wrapper import ChannelClosed, FromThreadChannel

try:
    import contextvars
except ImportError:
    contextvars = None  # type: ignore


pytestmark = pytest.mark.catch_loop_exceptions


thread_pool_implementation = (
    aiomisc.ThreadPoolExecutor,
    concurrent.futures.ThreadPoolExecutor,
)


thread_pool_ids = ("aiomisc pool", "default pool")


@pytest.fixture(params=thread_pool_implementation, ids=thread_pool_ids)
def thread_pool_executor(request):
    return request.param


@pytest.fixture(params=(aiomisc.threaded, aiomisc.threaded_separate))
def threaded_decorator(request, executor: aiomisc.ThreadPoolExecutor):
    assert executor
    return request.param


@pytest.fixture
def executor(event_loop: asyncio.AbstractEventLoop):
    thread_pool = aiomisc.ThreadPoolExecutor(8)
    event_loop.set_default_executor(thread_pool)
    try:
        yield thread_pool
    finally:
        with suppress(Exception):
            thread_pool.shutdown(wait=True)

        thread_pool.shutdown(wait=True)


async def test_from_thread_channel(threaded_decorator):
    channel = FromThreadChannel(maxsize=2)

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


async def test_from_thread_channel_wait_before(event_loop, threaded_decorator):
    channel = FromThreadChannel(maxsize=1)

    @threaded_decorator
    def in_thread():
        with channel:
            for i in range(10):
                channel.put(i)

    event_loop.call_later(0.1, in_thread)

    result = []
    with pytest.raises(ChannelClosed):
        while True:
            result.append(await asyncio.wait_for(channel.get(), timeout=5))

    assert result == list(range(10))


async def test_from_thread_channel_close(event_loop):
    channel = FromThreadChannel(maxsize=1)
    with channel:
        channel.put(1)

    with pytest.raises(ChannelClosed):
        channel.put(2)

    channel = FromThreadChannel(maxsize=1)
    task = event_loop.create_task(channel.get())

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=1)

    event_loop.call_soon(channel.put, 1)

    assert await channel.get() == 1


async def test_future_gc(thread_pool_executor, event_loop):
    thread_pool = thread_pool_executor(2)
    event = threading.Event()

    async def run():
        future = event_loop.create_future()

        cfuture = thread_pool.submit(time.sleep, 0.5)

        cfuture.add_done_callback(
            lambda *_: event_loop.call_soon_threadsafe(future.set_result, True)
        )

        weakref.finalize(cfuture, lambda *_: event.set())
        await future

    await run()

    gc.collect()
    event.wait(1)

    assert event.is_set()


async def test_threaded(threaded_decorator, timer):
    sleep = threaded_decorator(time.sleep)

    with timer(1):
        await asyncio.wait_for(
            asyncio.gather(sleep(1), sleep(1), sleep(1), sleep(1), sleep(1)),
            timeout=5,
        )


async def test_threaded_exc(threaded_decorator):
    @threaded_decorator
    def worker():
        raise Exception

    number = 90

    done, _ = await asyncio.wait([worker() for _ in range(number)], timeout=1)

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


async def test_cancel(executor, event_loop, timer):
    sleep = aiomisc.threaded(time.sleep)

    async with timeout(2):
        with timer(1, dispersion=2):
            tasks = [asyncio.ensure_future(sleep(1)) for _ in range(1000)]

            await asyncio.sleep(1)

            for task in tasks:
                task.cancel()

    executor.shutdown(wait=True)


async def test_simple(threaded_decorator, event_loop, timer):
    sleep = threaded_decorator(time.sleep)

    async with timeout(2):
        with timer(1):
            await asyncio.gather(sleep(1), sleep(1), sleep(1), sleep(1))


gen_decos = (aiomisc.threaded_iterable, aiomisc.threaded_iterable_separate)


@pytest.fixture(params=gen_decos)
def iterator_decorator(request):
    return request.param


async def test_threaded_generator(event_loop, timer):
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


async def test_threaded_generator_max_size(
    iterator_decorator, event_loop, timer
):
    @iterator_decorator(max_size=1)
    def arange(*args):
        return (yield from range(*args))

    async with timeout(2):
        count = 10

        result = []
        agen = arange(count)
        async for item in agen:
            result.append(item)

        assert result == list(range(count))


async def test_threaded_generator_exception(
    iterator_decorator, event_loop, timer
):
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


async def test_threaded_generator_close(iterator_decorator, event_loop, timer):
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
            async for _ in gen:
                counter += 1
                if counter > 9:
                    break

        wait_counter = 0
        while not stopped and wait_counter < 5:
            await asyncio.sleep(1)
            wait_counter += 1

        assert stopped


async def test_threaded_generator_close_cm(
    iterator_decorator, event_loop, timer
):
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
            async for _ in gen:
                counter += 1
                if counter > 9:
                    break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_close_break(
    iterator_decorator, event_loop, timer
):
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
        async for _ in noise():
            counter += 1
            if counter > 9:
                break

        stopped.wait(timeout=5)
        assert stopped.is_set()


async def test_threaded_generator_non_generator_raises(
    iterator_decorator, event_loop, timer
):
    @iterator_decorator()
    def errored():
        raise RuntimeError("Aaaaaaaa")

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored():
                pass


async def test_threaded_generator_func_raises(
    iterator_decorator, event_loop, timer
):
    @iterator_decorator
    def errored(val):
        if val:
            raise RuntimeError("Aaaaaaaa")

        yield

    async with timeout(2):
        with pytest.raises(RuntimeError):
            async for _ in errored(True):
                pass


@pytest.mark.skipif(contextvars is None, reason="no contextvars support")
async def test_context_vars(threaded_decorator, event_loop):
    ctx_var = contextvars.ContextVar("test")  # type: ignore

    @threaded_decorator
    def test(arg):
        value = ctx_var.get()
        assert value == arg * arg

    futures = []

    for i in range(8):
        ctx_var.set(i * i)
        futures.append(test(i))

    await asyncio.gather(*futures)


async def test_wait_coroutine_sync(threaded_decorator, event_loop):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1

    @threaded_decorator
    def test():
        aiomisc.sync_wait_coroutine(event_loop, coro)

    await test()
    assert result == 1


async def test_wait_coroutine_sync_current_loop(threaded_decorator):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1

    @threaded_decorator
    def test():
        aiomisc.wait_coroutine(coro())

    await test()
    assert result == 1


async def test_wait_awaitable(threaded_decorator):
    result = 0

    @threaded_decorator
    def in_thread():
        nonlocal result
        result += 1

    @threaded_decorator
    def test():
        aiomisc.sync_await(in_thread)

    await test()
    assert result == 1


async def test_wait_coroutine_sync_exc(threaded_decorator, event_loop):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1
        raise RuntimeError("Test")

    @threaded_decorator
    def test():
        aiomisc.sync_wait_coroutine(event_loop, coro)

    with pytest.raises(RuntimeError):
        await test()

    assert result == 1


async def test_wait_coroutine_sync_exc_noloop(threaded_decorator, event_loop):
    result = 0

    async def coro():
        nonlocal result
        await asyncio.sleep(1)
        result = 1
        raise RuntimeError("Test")

    @threaded_decorator
    def test():
        aiomisc.sync_wait_coroutine(None, coro)

    with pytest.raises(RuntimeError):
        await test()

    assert result == 1


def test_task_channel():
    channel = aiomisc.thread_pool.TaskChannel()
    events = []

    def consumer(event: threading.Event):
        try:
            while True:
                channel.get()(no_return=True)
        except aiomisc.thread_pool.TaskChannelCloseException:
            event.set()

    for _ in range(500):
        event = threading.Event()
        threading.Thread(target=consumer, args=(event,)).start()
        events.append(event)

    loop = asyncio.get_event_loop()
    future = loop.create_future()
    item = aiomisc.thread_pool.WorkItem(
        func=lambda x: None,
        loop=loop,
        future=future,
        statistic=aiomisc.thread_pool.ThreadPoolStatistic(),
    )

    for _ in range(10000):
        channel.put_nowait(item)

    channel.close()

    for event in events:
        event.wait(timeout=1)


async def test_threaded_class_func():
    @threaded
    def foo():
        return 42

    assert foo.sync_call() == 42
    assert await foo() == 42
    assert await foo.async_call() == 42


async def test_threaded_class_method():
    class TestClass:
        @threaded
        def foo(self):
            return 42

    instance = TestClass()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_class_staticmethod():
    class TestClass:
        @threaded
        @staticmethod
        def foo():
            return 42

    instance = TestClass()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_class_classmethod():
    class TestClass:
        @threaded
        @classmethod
        def foo(cls):
            return 42

    instance = TestClass()
    assert instance.foo.sync_call() == 42
    assert await instance.foo() == 42
    assert await instance.foo.async_call() == 42


async def test_threaded_iterator_class_func():
    @threaded_iterable
    def foo():
        yield 42

    assert list(foo.sync_call()) == [42]
    assert [x async for x in foo()] == [42]
    assert [x async for x in foo.async_call()] == [42]


async def test_threaded_iterator_class_method():
    class TestClass:
        @threaded_iterable
        def foo(self):
            yield 42

    instance = TestClass()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_iterator_class_staticmethod():
    class TestClass:
        @threaded_iterable
        @staticmethod
        def foo():
            yield 42

    instance = TestClass()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_iterator_class_classmethod():
    class TestClass:
        @threaded_iterable
        @classmethod
        def foo(cls):
            yield 42

    instance = TestClass()
    assert list(instance.foo.sync_call()) == [42]
    assert [x async for x in instance.foo()] == [42]
    assert [x async for x in instance.foo.async_call()] == [42]


async def test_threaded_generator_starts_in_aenter():
    """Test that the generator starts running when entering async context."""
    generator_started = threading.Event()

    @aiomisc.threaded_iterable(max_size=2)
    def gen():
        generator_started.set()
        yield 1
        yield 2
        yield 3

    async with timeout(2):
        async with gen() as iterator:
            # The generator should have started by now
            generator_started.wait(timeout=1)
            assert generator_started.is_set()

            # Verify we can still iterate
            result = [x async for x in iterator]
            assert result == [1, 2, 3]
