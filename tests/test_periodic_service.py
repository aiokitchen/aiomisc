import asyncio
from typing import Any

import pytest

import aiomisc
from aiomisc.service.periodic import PeriodicService

pytestmark = pytest.mark.catch_loop_exceptions


def test_str_representation():
    class FooPeriodicService(PeriodicService):
        async def callback(self) -> Any:
            pass

    svc = FooPeriodicService(interval=42, delay=4815162342)
    assert str(svc) == "FooPeriodicService(interval=42,delay=4815162342)"


def test_periodic(event_loop):
    counter = 0
    condition = asyncio.Condition()

    class CountPeriodicService(PeriodicService):
        async def callback(self):
            nonlocal counter
            nonlocal condition

            async with condition:
                counter += 1
                condition.notify_all()

    svc = CountPeriodicService(interval=0.1)

    async def assert_counter():
        nonlocal counter, svc

        counter = 0

        for i in (5, 10):
            async with condition:
                await asyncio.wait_for(
                    condition.wait_for(lambda: counter >= i), timeout=10
                )
            assert counter == i

    with aiomisc.entrypoint(svc, loop=event_loop) as loop:
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))


def test_delay(event_loop):
    counter = 0
    condition = asyncio.Condition()

    class CountPeriodicService(PeriodicService):
        async def callback(self):
            nonlocal counter

            async with condition:
                counter += 1
                condition.notify_all()

    svc = CountPeriodicService(interval=0.1, delay=0.5)

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        await asyncio.sleep(0.25)
        assert not counter

        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == 5), timeout=5
            )

        await svc.stop(None)

    with aiomisc.entrypoint(svc, loop=event_loop) as loop:
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))


def test_stop_from_callback(event_loop):
    # Regression test for https://github.com/aiokitchen/aiomisc/issues/250
    class SelfStopping(PeriodicService):
        calls = 0

        async def callback(self) -> None:
            self.calls += 1
            if self.calls == 2:
                await self.stop()

    svc = SelfStopping(interval=0.05)

    with aiomisc.entrypoint(svc, loop=event_loop) as loop:
        loop.call_later(1.0, loop.stop)
        loop.run_forever()

    assert svc.calls == 2, "no callbacks must run after the service stopped"
