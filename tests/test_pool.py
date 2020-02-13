import asyncio
import pytest

import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


async def test_base_class(loop: asyncio.AbstractEventLoop):
    with pytest.raises(TypeError):
        aiomisc.PoolBase()


class SimplePool(aiomisc.PoolBase):
    async def _create_instance(self):
        return self._loop.create_future()

    async def _destroy_instance(self, instance):
        if instance.done():
            return

        instance.set_result(True)

    async def _check_instance(self, instance):
        return not instance.done()


async def test_simple_pool_no_reuse_context_manager(loop):
    size = 5
    recycle = 1

    pool = SimplePool(maxsize=size, recycle=recycle)

    cm = pool.acquire()

    async with cm as future:
        assert not future.done()

    with pytest.raises(RuntimeError):
        async with cm:
            pass

    await pool.close()


async def test_simple_pool_recycle(loop):
    size = 5
    recycle = 1

    pool = SimplePool(maxsize=size, recycle=recycle)

    futures = []

    def on_fail(future):
        if future.done():
            return

        future.set_exception(TimeoutError)

    async def run():
        async with pool.acquire() as future:
            assert not future.done()
            futures.append(future)
            loop.call_later(5 * recycle, on_fail, future)

    await asyncio.gather(*[run() for _ in range(size)])
    assert len(pool) == size

    await asyncio.sleep(2 * recycle)

    async def run():
        async with pool.acquire():
            pass

    await asyncio.gather(*[run() for _ in range(size)])

    await asyncio.gather(*futures)
    await pool.close()


async def test_simple_pool_check_before(loop):
    size = 5
    pool = SimplePool(maxsize=size, recycle=None)

    futures = set()

    for _ in range(size * 2):
        async with pool.acquire() as future:
            assert not future.done()
            futures.add(future)
            future.set_result(True)

    assert len(futures) == size * 2

    await asyncio.wait_for(asyncio.gather(*futures), timeout=1)

    await pool.close()


async def test_simple_pool_check_after(loop):
    size = 5
    pool = SimplePool(maxsize=size, recycle=None)

    futures = set()

    for _ in range(size * 2):
        # Switch context
        await asyncio.sleep(0)

        async with pool.acquire() as future:
            assert not future.done()
            futures.add(future)
            loop.call_soon(future.set_result, True)

    assert len(futures) == size * 2
    await asyncio.gather(*futures)
    await pool.close()


async def test_simple_pool_parallel(loop):
    size = 5
    pool = SimplePool(maxsize=size, recycle=None)

    async def run():
        async with pool.acquire() as future:
            assert not future.done()

    tasks = [loop.create_task(run()) for _ in range(1000)]

    await asyncio.gather(*tasks)

    assert len(pool) == size
    await pool.close()


async def test_simple_pool_parallel_broken_instances(loop):
    size = 5
    pool = SimplePool(maxsize=size, recycle=None)

    async def run():
        async with pool.acquire() as future:
            assert not future.done()
            future.set_result(True)

    tasks = [loop.create_task(run()) for _ in range(1000)]

    await asyncio.gather(*tasks)

    assert len(pool) == size
    await pool.close()
