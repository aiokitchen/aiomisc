import asyncio

import pytest

import aiomisc
from aiomisc.service.cron import CronService


pytestmark = pytest.mark.catch_loop_exceptions


def test_str_representation():
    class FooCronService(CronService):
        ...

    svc = FooCronService(spec="* * * * * *")
    assert str(svc) == "FooCronService(spec=* * * * * *)"


def test_cron():
    counter = 0

    class CountCronService(CronService):
        async def callback(self):
            nonlocal counter
            counter += 1
            await asyncio.sleep(0)

    svc = CountCronService(spec="* * * * * *")

    async def assert_counter():
        nonlocal counter, svc

        counter = 0
        await asyncio.sleep(1)
        assert counter == 1

        await svc.stop()

        await asyncio.sleep(1)
        assert counter == 1

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(asyncio.wait_for(assert_counter(), timeout=10))
