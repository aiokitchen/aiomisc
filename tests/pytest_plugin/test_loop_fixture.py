import asyncio
import socket

import pytest

from aiomisc import Service


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


try:
    from .yield_fixture_native import yield_fixture
except SyntaxError:
    from .yield_fixture import yield_fixture  # noqa


async def test_yield_fixture(yield_fixture):  # noqa
    assert yield_fixture is True


def test_localhost(localhost):
    assert socket.gethostbyname("localhost") == localhost
