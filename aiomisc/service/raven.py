import asyncio
import inspect
import logging
import socket
import typing as t
from types import MappingProxyType

import yarl
from aiohttp import ClientSession, TCPConnector
from raven import Client  # type: ignore
from raven.handlers.logging import SentryHandler  # type: ignore
from raven.transport import Transport  # type: ignore
from raven_aiohttp import QueuedAioHttpTransport  # type: ignore

from aiomisc.service import Service


log = logging.getLogger(__name__)


class DummyTransport(Transport):         # type: ignore
    def send(self, url, data, headers):  # type: ignore
        pass


class QueuedKeepaliveAioHttpTransport(QueuedAioHttpTransport):  # type: ignore
    DNS_CACHE_TTL = 600
    DNS_CACHE = True
    TCP_CONNECTION_LIMIT = 32
    TCP_CONNECTION_LIMIT_HOST = 8
    WORKERS = 1
    QUEUE_SIZE = 1000

    def __init__(
        self, *args: t.Any, family: int = socket.AF_UNSPEC,
        loop: asyncio.AbstractEventLoop = None,
        dns_cache: bool = DNS_CACHE,
        dns_cache_ttl: int = DNS_CACHE_TTL,
        connection_limit: int = TCP_CONNECTION_LIMIT,
        connection_limit_host: int = TCP_CONNECTION_LIMIT_HOST,
        workers: int = WORKERS, qsize: int = QUEUE_SIZE, **kwargs: t.Any
    ):
        self.connection_limit = connection_limit
        self.connection_limit_host = connection_limit_host
        self.dns_cache = dns_cache
        self.dns_cache_ttl = dns_cache_ttl

        super().__init__(
            *args, family=family, loop=loop, keepalive=True,
            workers=workers, qsize=qsize, **kwargs
        )

    def _client_session_factory(self) -> ClientSession:
        self.connector = TCPConnector(
            family=self.family,
            limit=self.connection_limit,
            limit_per_host=self.connection_limit_host,
            ttl_dns_cache=self.dns_cache_ttl,
            use_dns_cache=self.dns_cache,
            verify_ssl=self.verify_ssl,
        )

        return ClientSession(
            connector=self.connector,
            connector_owner=False,
        )

    async def _close(self) -> Transport:
        transport = await super()._close()
        if inspect.iscoroutinefunction(self.connector.close()):
            await self.connection.close()
        else:
            self.connector.close()
        return transport


class RavenSender(Service):
    __required__ = "sentry_dsn",

    sentry_dsn = None  # type: yarl.URL
    min_level = logging.WARNING  # type: int
    client_options = MappingProxyType({})  # type: t.Mapping

    client = None  # type: Client

    filters = ()  # type: t.Iterable[logging.Filter]

    async def start(self) -> None:
        self.client = Client(
            str(self.sentry_dsn),
            transport=QueuedKeepaliveAioHttpTransport,
            **self.client_options
        )

        # Initialize Transport object
        self.client.remote.get_transport()

        self.sentry_dsn = yarl.URL(
            self.sentry_dsn,
        ).with_password("").with_user("")

        log.info("Starting Raven for %r", self.sentry_dsn)

        handler = SentryHandler(
            client=self.client,
            level=self.min_level,
        )

        # Add filters
        for fltr in self.filters:
            handler.addFilter(fltr)

        logging.getLogger().handlers.append(
            handler,
        )

    async def stop(self, *_: t.Any) -> None:
        transport = self.client.remote.get_transport()
        self.client.set_dsn("", transport=DummyTransport)

        await transport.close()

        log.info("Stopping Raven client for %r", self.sentry_dsn)


__all__ = ("RavenSender",)
