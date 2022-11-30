import abc
import asyncio
import logging
import socket
from http import HTTPStatus
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional, Set

import aiohttp
import yarl
from aiohttp import ClientSession, TCPConnector
from raven import Client  # type: ignore
from raven.conf import defaults  # type: ignore
from raven.exceptions import APIError, RateLimited  # type: ignore
from raven.handlers.logging import SentryHandler  # type: ignore
from raven.transport import Transport  # type: ignore
from raven.transport.base import AsyncTransport  # type: ignore
from raven.transport.http import HTTPTransport  # type: ignore

from aiomisc.service import Service
from aiomisc.utils import TimeoutType


log = logging.getLogger(__name__)


__doc__ = """
This module based on https://github.com/getsentry/raven-aiohttp

Copyright (c) 2018 Functional Software, Inc and individual contributors.
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

    1. Redistributions of source code must retain the above copyright notice,
    this list of conditions and the following disclaimer.

    2. Redistributions in binary form must reproduce the above copyright
    notice, this list of conditions and the following disclaimer in the
    documentation and/or other materials provided with the distribution.

    3. Neither the name of the Raven nor the names of its contributors may be
    used to endorse or promote products derived from this software without
    specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
"""


class DummyTransport(Transport):         # type: ignore
    def send(self, url, data, headers):  # type: ignore
        pass


class AioHttpTransportBase(
    AsyncTransport, HTTPTransport, metaclass=abc.ABCMeta,    # type: ignore
):

    def __init__(
        self, parsed_url: Optional[str] = None, *, verify_ssl: bool = True,
        timeout: TimeoutType = defaults.TIMEOUT, keepalive: bool = True,
        family: int = socket.AF_INET,
    ):
        self._keepalive = keepalive
        self._family = family
        self._loop = asyncio.get_event_loop()

        if parsed_url is not None:
            raise TypeError(
                "Transport accepts no URLs for this version of raven.",
            )
        super().__init__(timeout, verify_ssl)

        if self.keepalive:
            self._client_session = self._client_session_factory()

        self._closing = False

    @property
    def keepalive(self) -> bool:
        return self._keepalive

    @property
    def family(self) -> int:
        return self._family

    def _client_session_factory(self) -> aiohttp.ClientSession:
        connector = aiohttp.TCPConnector(
            verify_ssl=self.verify_ssl, family=self.family,
        )
        return aiohttp.ClientSession(
            connector=connector,
        )

    async def _do_send(
        self, url: str, data: Any, headers: Mapping,
        callback: Callable[[], Any], errorback: Callable[[Any], Any],
    ) -> None:
        if self.keepalive:
            session = self._client_session
        else:
            session = self._client_session_factory()

        resp = None

        try:
            resp = await session.post(
                url, data=data, compress=False,
                headers=headers, timeout=self.timeout,
            )

            code = resp.status
            if code != HTTPStatus.OK:
                msg = resp.headers.get("x-sentry-error")
                if code == HTTPStatus.TOO_MANY_REQUESTS:
                    try:
                        retry_after = int(resp.headers.get("retry-after", "0"))
                    except (ValueError, TypeError):
                        retry_after = 0
                    errorback(RateLimited(msg, retry_after))
                else:
                    errorback(APIError(msg, code))
            else:
                callback()
        except asyncio.CancelledError:
            # do not mute asyncio.CancelledError
            raise
        except Exception as exc:
            errorback(exc)
        finally:
            if resp is not None:
                resp.release()
            if not self.keepalive:
                await session.close()

    @abc.abstractmethod
    def _async_send(
        self, url: str, data: Any, headers: Mapping,
        success_cb: Callable[[], Any], failure_cb: Callable[[Any], Any],
    ) -> None:  # pragma: no cover
        pass

    @abc.abstractmethod
    async def _close(self) -> None:  # pragma: no cover
        pass

    def async_send(
        self, url: str, data: Any, headers: Mapping,
        success_cb: Callable[[], Any], failure_cb: Callable[[Any], Any],
    ) -> None:
        if self._closing:
            failure_cb(RuntimeError(f"{self.__class__.__name__} is closed"))
            return

        self._loop.call_soon_threadsafe(
            self._async_send, url, data, headers, success_cb, failure_cb,
        )

    async def _close_coro(
        self,
        *,
        timeout: Optional[TimeoutType] = None,
    ) -> None:
        try:
            await asyncio.wait_for(
                self._close(), timeout=timeout,
            )
        except asyncio.TimeoutError:
            pass
        finally:
            if self.keepalive:
                await self._client_session.close()

    def close(self, *, timeout: Optional[TimeoutType] = None) -> Awaitable[Any]:
        if self._closing:
            async def dummy() -> None:
                pass

            return dummy()

        self._closing = True

        return self._loop.create_task(self._close_coro(timeout=timeout))


class AioHttpTransport(AioHttpTransportBase):

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

        self._tasks: Set[asyncio.Task] = set()

    def _async_send(
        self, url: str, data: Any, headers: Mapping,
        success_cb: Callable[[], Any], failure_cb: Callable[[Any], Any],
    ) -> None:
        coro = self._do_send(url, data, headers, success_cb, failure_cb)

        task = self._loop.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.remove)

    async def _close(self) -> None:
        await asyncio.gather(
            *self._tasks,
            return_exceptions=True,
        )

        assert len(self._tasks) == 0


class QueuedAioHttpTransport(AioHttpTransportBase):

    def __init__(
        self, *args: Any, workers: int = 1, qsize: int = 1000, **kwargs: Any,
    ):
        super().__init__(*args, **kwargs)

        self._queue: asyncio.Queue = asyncio.Queue(maxsize=qsize)

        self._workers = set()

        for _ in range(workers):
            worker: asyncio.Task = self._loop.create_task(self._worker())
            self._workers.add(worker)
            worker.add_done_callback(self._workers.remove)

    async def _worker(self) -> None:
        while True:
            data = await self._queue.get()

            try:
                if data is ...:
                    self._queue.put_nowait(...)
                    break

                url, data, headers, success_cb, failure_cb = data

                await self._do_send(
                    url, data, headers, success_cb, failure_cb,
                )
            finally:
                self._queue.task_done()

    def _async_send(
        self, url: str, data: Any, headers: Mapping,
        callback: Callable[[], Any], errorback: Callable[[Any], Any],
    ) -> None:
        payload = url, data, headers, callback, errorback

        try:
            self._queue.put_nowait(payload)
        except asyncio.QueueFull:
            skipped = self._queue.get_nowait()
            self._queue.task_done()

            *_, errorback = skipped

            errorback(
                RuntimeError("QueuedAioHttpTransport internal queue is full"),
            )

            self._queue.put_nowait(payload)

    async def _close(self) -> None:
        try:
            self._queue.put_nowait(...)
        except asyncio.QueueFull:
            skipped = self._queue.get_nowait()
            self._queue.task_done()

            *_, failure_cb = skipped

            failure_cb(
                RuntimeError("QueuedAioHttpTransport internal queue was full"),
            )

            self._queue.put_nowait(...)

        await asyncio.gather(
            *self._workers,
            return_exceptions=True,
        )

        assert len(self._workers) == 0
        assert self._queue.qsize() == 1
        try:
            assert self._queue.get_nowait() is ...
        finally:
            self._queue.task_done()


class QueuedKeepaliveAioHttpTransport(QueuedAioHttpTransport):
    DNS_CACHE_TTL = 600
    DNS_CACHE = True
    TCP_CONNECTION_LIMIT = 32
    TCP_CONNECTION_LIMIT_HOST = 8
    WORKERS = 1
    QUEUE_SIZE = 1000

    def __init__(
        self, *args: Any, family: int = socket.AF_UNSPEC,
        dns_cache: bool = DNS_CACHE,
        dns_cache_ttl: int = DNS_CACHE_TTL,
        connection_limit: int = TCP_CONNECTION_LIMIT,
        connection_limit_host: int = TCP_CONNECTION_LIMIT_HOST,
        workers: int = WORKERS, qsize: int = QUEUE_SIZE, **kwargs: Any,
    ):
        self.connection_limit = connection_limit
        self.connection_limit_host = connection_limit_host
        self.dns_cache = dns_cache
        self.dns_cache_ttl = dns_cache_ttl

        super().__init__(
            *args, family=family, keepalive=True,
            workers=workers, qsize=qsize, **kwargs,
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

    async def _close(self) -> None:
        await super()._close()
        await self.connector.close()


class RavenSender(Service):
    __required__ = "sentry_dsn",

    sentry_dsn: yarl.URL
    min_level: int = logging.WARNING
    client_options: Mapping[str, Any] = MappingProxyType({})
    client: Client
    filters: Iterable[logging.Filter] = ()

    async def start(self) -> None:
        self.client = Client(
            str(self.sentry_dsn),
            transport=QueuedKeepaliveAioHttpTransport,
            **self.client_options,
        )

        # Initialize Transport object
        self.client.remote.get_transport()

        self.sentry_dsn = yarl.URL(
            self.sentry_dsn,
        ).with_password("").with_user("")

        log.info("Starting Raven for %r", self.sentry_dsn)

        handler = SentryHandler(client=self.client, level=self.min_level)

        # Add filters
        for fltr in self.filters:
            handler.addFilter(fltr)

        logging.getLogger().handlers.append(handler)

    async def stop(self, *_: Any) -> None:
        transport = self.client.remote.get_transport()
        self.client.set_dsn("", transport=DummyTransport)

        await transport.close()

        log.info("Stopping Raven client for %r", self.sentry_dsn)


__all__ = ("RavenSender",)
