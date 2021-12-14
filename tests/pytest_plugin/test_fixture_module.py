import asyncio
import pytest
from aiomisc import entrypoint


@pytest.fixture(scope='module')
def loop():
    with entrypoint() as loop:
        asyncio.set_event_loop(loop)
        yield loop


@pytest.fixture(scope='module')
async def sample_fixture(loop):
    yield 1


LOOP_ID = None


async def test_using_fixture(sample_fixture):
    global LOOP_ID
    LOOP_ID = id(asyncio.get_event_loop())
    assert sample_fixture == 1


async def test_not_using_fixture(loop):
    assert id(loop) == LOOP_ID
