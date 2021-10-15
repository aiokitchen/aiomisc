import asyncio
import logging
import socket
import sys
from typing import Callable

import pytest

from aiomisc import Service
from aiomisc_pytest.pytest_plugin import PortSocket


class _TestService(Service):
    loop_on_init = None  # type: asyncio.AbstractEventLoop

    async def start(self):
        assert self.loop is asyncio.get_event_loop()


@pytest.fixture()
async def async_sleep(loop):
    f = loop.create_future()
    loop.call_soon(f.set_result, True)
    return await f


@pytest.fixture()
def service(loop: asyncio.AbstractEventLoop):
    return _TestService(loop_on_init=loop)


@pytest.fixture()
def services(service: _TestService, async_sleep):
    return [service]


async def test_loop_fixture(
    service: _TestService,
    loop: asyncio.AbstractEventLoop,
):
    assert service.loop is service.loop_on_init is loop


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


async def test_yield_fixture(yield_fixture):  # noqa
    assert yield_fixture is True


def test_localhost(localhost):
    assert socket.gethostbyname("localhost") == localhost


@pytest.mark.skipif(sys.version_info > (3, 6), reason="skip python 3.6")
def test_aiomisc_socket_factory(
    aiomisc_socket_factory: Callable[..., PortSocket],
):
    result = aiomisc_socket_factory(socket.AF_INET, socket.SOCK_STREAM)
    assert result.port > 0
    assert result.socket.family == socket.AF_INET
    assert result.socket.type == socket.SOCK_STREAM

    result = aiomisc_socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
    assert result.port > 0
    assert result.socket.family == socket.AF_INET
    assert result.socket.type == socket.SOCK_DGRAM
