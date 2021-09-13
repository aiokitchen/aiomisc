import asyncio
import logging

import pytest


@pytest.fixture
async def yield_fixture():
    logging.info("Setup")
    await asyncio.sleep(0)
    yield True
    await asyncio.sleep(0)
    logging.info("Teardown")


async def test_yield_fixture(yield_fixture):
    assert yield_fixture is True
