import asyncio

import pytest

import aiomisc
from aiomisc.service.periodic import PeriodicService


pytestmark = pytest.mark.catch_loop_exceptions


def test_str_representation():
    class FooPeriodicService(PeriodicService):
        ...

    svc = FooPeriodicService(interval=42, delay=4815162342)
    assert str(svc) == "FooPeriodicService(interval=42,delay=4815162342)"


def test_periodic():
    counter = 0
    condition = None

    class CountPeriodicService(PeriodicService):
        async def callback(self):
            nonlocal counter
            counter += 1
            await asyncio.sleep(0)

    svc = CountPeriodicService(interval=0.1)

    async def assert_counter():
        nonlocal counter, svc

        counter = 0

        for i in (5, 10, 15):
            async with condition:
                await asyncio.wait_for(
                    condition.wait_for(lambda: counter == i),
                    timeout=2
                )

            await svc.stop(None)
            assert counter == i

    with aiomisc.entrypoint(svc) as loop:
        condition = asyncio.Condition()
        loop.run_until_complete(
            asyncio.wait_for(
                assert_counter(),
                timeout=10
            )
        )


def test_delay():
    counter = 0

    class CountPeriodicService(PeriodicService):
        async def callback(self):
            nonlocal counter
            counter += 1
            await asyncio.sleep(0)

    svc = CountPeriodicService(interval=0.1, delay=0.5)

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        await asyncio.sleep(0.25)
        assert not counter

        await asyncio.sleep(0.5)

        await svc.stop(None)

        assert 1 < counter < 4

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))
