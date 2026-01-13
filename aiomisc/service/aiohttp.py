import asyncio
import socket
import ssl
from collections.abc import Iterable, Mapping
from contextlib import suppress
from typing import Any

from aiohttp.web import Application, AppRunner, BaseRunner, SockSite

from aiomisc.service.tls import PathOrStr, SSLOptions

from ..utils import bind_socket
from .base import Service

try:
    from aiohttp.web_log import AccessLogger
except ImportError:  # pragma: nocover
    from aiohttp.helpers import AccessLogger  # type: ignore


RunnerKwargsType = Mapping[str, Any] | Iterable[tuple[str, Any]]


class AIOHTTPService(Service):
    __async_required__: tuple[str, ...] = ("start", "create_application")

    site: SockSite
    runner: BaseRunner
    handler_cancellation: bool = True

    def __init__(
        self,
        address: str | None = "localhost",
        port: int | None = None,
        sock: socket.socket | None = None,
        shutdown_timeout: int = 5,
        handler_cancellation: bool = handler_cancellation,
        runner_kwargs: RunnerKwargsType | None = None,
        **kwds: Any,
    ):
        if not sock:
            if not (address and port):
                raise RuntimeError(
                    "You should pass socket instance or "
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                address=address, port=port, proto_name="http"
            )

        elif not isinstance(sock, socket.socket):
            raise ValueError("sock must be socket instance")
        else:
            self.socket = sock

        self.shutdown_timeout = shutdown_timeout

        self.runner_kwargs: dict[str, Any] = dict(runner_kwargs or {})
        self.runner_kwargs.setdefault("access_log_class", AccessLogger)
        self.runner_kwargs.setdefault(
            "access_log_format", AccessLogger.LOG_FORMAT
        )
        self.runner_kwargs.setdefault(
            "handler_cancellation", handler_cancellation
        )

        super().__init__(**kwds)

    async def create_application(self) -> Application:
        return Application()

    async def create_site(self) -> SockSite:
        if getattr(self, "runner", None) is None:
            raise RuntimeError("runner already created")

        return SockSite(self.runner, self.socket)

    async def make_runner(self, application: Application) -> AppRunner:
        return AppRunner(
            application,
            shutdown_timeout=self.shutdown_timeout,
            **self.runner_kwargs,
        )

    async def start(self) -> None:
        if hasattr(self, "runner"):
            raise RuntimeError("Can not start twice")

        application: Application = await self.create_application()
        self.runner = await self.make_runner(application)
        await self.runner.setup()

        self.site = await self.create_site()
        await self.site.start()

    async def stop(self, exception: Exception | None = None) -> None:
        try:
            if self.site:
                await self.site.stop()
        finally:
            # Ensure all handlers are finished
            await asyncio.sleep(0)
            if hasattr(self, "runner"):
                # Avoid AttributeError in case server already dereferenced
                with suppress(AttributeError):
                    await self.runner.cleanup()


class AIOHTTPSSLService(AIOHTTPService):
    def __init__(
        self,
        cert: PathOrStr,
        key: PathOrStr,
        ca: PathOrStr | None = None,
        address: str | None = None,
        port: int | None = None,
        verify: bool = True,
        sock: socket.socket | None = None,
        shutdown_timeout: int = 5,
        require_client_cert: bool = False,
        **kwds: Any,
    ):
        super().__init__(
            address=address,
            port=port,
            sock=sock,
            shutdown_timeout=shutdown_timeout,
            **kwds,
        )

        self.__ssl_options = SSLOptions(
            cert, key, ca, verify, require_client_cert, ssl.Purpose.CLIENT_AUTH
        )

    async def create_site(self) -> SockSite:
        assert self.runner and self.socket

        return SockSite(
            self.runner,
            self.socket,
            ssl_context=await self.loop.run_in_executor(
                None, self.__ssl_options.create_context
            ),
        )
