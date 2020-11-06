import logging

import pytest


@pytest.fixture
async def yield_fixture(loop):
    logging.info("Setup")

    f = loop.create_future()
    loop.call_later(0, f.set_result, True)
    await f

    try:
        yield True
    finally:
        f = loop.create_future()
        loop.call_later(0, f.set_result, True)
        await f

        logging.info("Teardown")
