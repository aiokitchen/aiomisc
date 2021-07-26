import asyncio
import logging

import pytest
from async_generator import async_generator, yield_


@pytest.fixture
@async_generator
async def yield_fixture():
    logging.info("Setup")
    await asyncio.sleep(0)
    await yield_(True)
    await asyncio.sleep(0)
    logging.info("Teardown")


async def test_yield_fixture(yield_fixture):
    assert yield_fixture is True
