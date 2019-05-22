import asyncio
import pytest

import aiomisc
from aiomisc.service.periodic import PeriodicService


pytestmark = pytest.mark.catch_loop_exceptions


def test_str_representation():
    class FooPeriodicService(PeriodicService):
        ...

    svc = FooPeriodicService(interval=42)
    assert str(svc) == 'FooPeriodicService(interval=42)'


def test_periodic():
    counter = 0

    class CountPeriodicService(PeriodicService):
        async def callback(self):
            nonlocal counter
            counter += 1
            await asyncio.sleep(0)

    svc = CountPeriodicService(interval=0.1)

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        await asyncio.sleep(0.5)
        assert 4 <= counter <= 7

        await svc.stop(None)

        await asyncio.sleep(0.5)
        assert 4 <= counter <= 7

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(assert_counter())
