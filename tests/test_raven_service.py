from typing import Any

import pytest
from aiohttp import web
from yarl import URL

import aiomisc
from aiomisc import bind_socket
from aiomisc.service.aiohttp import AIOHTTPService
from aiomisc.service.raven import RavenSender

pytestmark = pytest.mark.catch_loop_exceptions


class REST(AIOHTTPService):
    @staticmethod
    async def handle(request: web.Request) -> Any:
        raise ValueError("Some error in handle handler")

    async def create_application(self):
        app = web.Application()
        app.router.add_route("GET", "/exc", self.handle)
        app.router.add_route("GET", "/project-test", self.handle)
        return app


@pytest.fixture
def mock_sentry(localhost, aiomisc_unused_port_factory):
    port = aiomisc_unused_port_factory()
    with bind_socket(address=localhost, port=port) as sock:
        rest = REST(sock=sock)
        yield (
            rest,
            URL.build(
                scheme="http",
                user="test",
                password="test",
                port=port,
                host=localhost,
                path="/project-test",
            ),
        )


def test_raven_create(mock_sentry):
    mock_sentry_service, mock_sentry_url = mock_sentry
    svc = RavenSender(sentry_dsn=mock_sentry_url)

    with aiomisc.entrypoint(svc, mock_sentry_service):
        pass
