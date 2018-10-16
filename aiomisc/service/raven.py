import logging

import yarl
from aiomisc.service import Service
from raven import Client
from raven.handlers.logging import SentryHandler
from raven.transport import Transport
from raven_aiohttp import AioHttpTransport


log = logging.getLogger(__name__)


class DummyTransport(Transport):
    def send(self, url, data, headers):
        pass


class RavenSender(Service):
    sentry_dsn = None               # type: yarl.URL
    client = None                   # type: Client
    min_level = logging.WARNING     # type: int

    async def start(self):
        self.client = Client(
            str(self.sentry_dsn),
            transport=AioHttpTransport
        )

        self.sentry_dsn = yarl.URL(
            self.sentry_dsn
        ).with_password('').with_user('')

        log.info('Starting Raven for %r', self.sentry_dsn)

        handler = SentryHandler(
            client=self.client,
            level=self.min_level
        )
        handler.setLevel(self.min_level)

        logging.getLogger().handlers.append(
            handler
        )

    async def stop(self, *_):
        transport = self.client.remote.get_transport()
        self.client.set_dsn('', transport=DummyTransport)

        await transport.close()

        log.info('Stopping Raven client for %r', self.sentry_dsn)


__all__ = ('RavenSender',)
