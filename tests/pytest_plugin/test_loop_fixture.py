import asyncio

import pytest

from aiomisc import Service


class _TestService(Service):
    loop_on_init = None  # type: asyncio.AbstractEventLoop

    async def start(self):
        assert self.loop is asyncio.get_event_loop()


@pytest.fixture()
def service(loop: asyncio.AbstractEventLoop):
    return _TestService(loop_on_init=loop)


@pytest.fixture()
def services(service: _TestService):
    return [service]


async def test_loop_fixture(service: _TestService,
                            loop: asyncio.AbstractEventLoop):
    assert service.loop is service.loop_on_init is loop
