import asyncio
import pytest

from aiomisc.periodic import PeriodicCallback


@pytest.mark.asyncio
async def test_periodic(event_loop):
    counter = 0

    def task():
        nonlocal counter
        counter += 1

    periodic = PeriodicCallback(task)
    periodic.start(0.1, event_loop)

    await asyncio.sleep(0.5, loop=event_loop)
    periodic.stop()

    assert 4 < counter < 7

    await asyncio.sleep(0.5, loop=event_loop)

    assert 4 < counter < 7
