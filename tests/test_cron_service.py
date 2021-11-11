import asyncio

import pytest

import aiomisc
from aiomisc.service.cron import CronService


pytestmark = pytest.mark.catch_loop_exceptions


def test_str_representation():
    class FooCronService(CronService):
        async def callback(self):
            pass

    svc = FooCronService()

    async def runner():
        pass

    svc.register(runner, "* * * * * *")
    assert str(svc) == "FooCronService(CronCallback(runner): * * * * * *)"


def test_cron():
    counter = 0
    condition = None

    async def callback():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    svc = CronService()

    svc.register(callback, spec="* * * * * *")

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == 1),
                timeout=2,
            )

        await svc.stop()

        await asyncio.sleep(1)
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda: counter == 1),
                timeout=2,
            )

        assert counter == 1

    with aiomisc.entrypoint(svc) as loop:
        condition = asyncio.Condition()

        loop.run_until_complete(
            asyncio.wait_for(
                assert_counter(),
                timeout=10,
            ),
        )


def test_register():
    counter = 0
    condition = None

    async def callback():
        nonlocal counter
        async with condition:
            counter += 1
            condition.notify_all()

    svc = CronService()

    svc.register(callback, spec="* * * * * *")
    svc.register(callback, spec="* * * * * */2")  # even second
    svc.register(callback, spec="* * * * * *")

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        async with condition:
            await asyncio.wait_for(
                condition.wait_for(lambda:  4 < counter <= 10),
                timeout=10,
            )

        await svc.stop()

        await asyncio.sleep(1)
        assert counter >= 5

    with aiomisc.entrypoint(svc) as loop:
        condition = asyncio.Condition()
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))
