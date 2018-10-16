import logging
from types import MappingProxyType
from typing import Mapping  # NOQA

import yarl
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.transport import Transport
from raven_aiohttp import AioHttpTransport

from aiomisc.service import Service


log = logging.getLogger(__name__)


class DummyTransport(Transport):
    def send(self, url, data, headers):
        pass


class RavenSender(Service):
    sentry_dsn = None  # type: yarl.URL
    min_level = logging.WARNING  # type: int
    client_options = MappingProxyType({})  # type: Mapping

    client = None  # type: Client

    async def start(self):
        self.client = Client(
            str(self.sentry_dsn),
            transport=AioHttpTransport,
            **self.client_options
        )

        self.sentry_dsn = yarl.URL(
            self.sentry_dsn
        ).with_password('').with_user('')

        log.info('Starting Raven for %r', self.sentry_dsn)

        handler = SentryHandler(
            client=self.client,
            level=self.min_level
        )

        logging.getLogger().handlers.append(
            handler
        )

    async def stop(self, *_):
        transport = self.client.remote.get_transport()
        self.client.set_dsn('', transport=DummyTransport)

        await transport.close()

        log.info('Stopping Raven client for %r', self.sentry_dsn)


__all__ = ('RavenSender',)
