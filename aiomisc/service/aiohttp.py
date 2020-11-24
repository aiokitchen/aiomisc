import socket
import typing as t

from aiohttp.web import Application, AppRunner, BaseRunner, SockSite  # noqa

from aiomisc.service.tls import PathOrStr, get_ssl_context

from ..utils import bind_socket
from .base import Service


try:
    from aiohttp.web_log import AccessLogger
except ImportError:         # pragma: nocover
    from aiohttp.helpers import AccessLogger  # type: ignore


class AIOHTTPService(Service):
    __async_required__ = (
        "start", "create_application"
    )   # type: t.Tuple[str, ...]

    def __init__(
        self, address: t.Optional[str] = "localhost", port: int = None,
        sock: socket.socket = None, shutdown_timeout: int = 5,
        **kwds: t.Any
    ):

        if not sock:
            if not (address and port):
                raise RuntimeError(
                    "You should pass socket instance or "
                    '"address" and "port" couple',
                )

            self.socket = bind_socket(
                address=address,
                port=port,
                proto_name="http",
            )

        elif not isinstance(sock, socket.socket):
            raise ValueError("sock must be socket instance")
        else:
            self.socket = sock

        self.runner = None      # type: t.Optional[BaseRunner]
        self.site = None        # type: t.Optional[SockSite]
        self.shutdown_timeout = shutdown_timeout

        super().__init__(**kwds)

    async def create_application(self) -> Application:
        raise NotImplementedError(
            "You should implement "
            '"create_application" method',
        )

    async def create_site(self) -> SockSite:
        if self.runner is None:
            raise RuntimeError

        return SockSite(
            self.runner, self.socket,
            shutdown_timeout=self.shutdown_timeout,
        )

    async def start(self) -> None:
        if self.runner is not None:
            raise RuntimeError("Can not start twice")

        self.runner = AppRunner(
            await self.create_application(),
            access_log_class=AccessLogger,
            access_log_format=AccessLogger.LOG_FORMAT,
        )

        await self.runner.setup()

        self.site = await self.create_site()

        await self.site.start()

    async def stop(self, exception: Exception = None) -> None:
        try:
            if self.site:
                await self.site.stop()
        finally:
            if self.runner:
                await self.runner.cleanup()


class AIOHTTPSSLService(AIOHTTPService):
    def __init__(
        self, cert: PathOrStr, key: PathOrStr, ca: PathOrStr = None,
        address: str = None, port: int = None, verify: bool = True,
        sock: socket.socket = None, shutdown_timeout: int = 5,
        require_client_cert: bool = False, **kwds: t.Any
    ):

        super().__init__(
            address=address, port=port, sock=sock,
            shutdown_timeout=shutdown_timeout, **kwds
        )

        self.__ssl_options = cert, key, ca, verify, require_client_cert

    async def create_site(self) -> SockSite:
        assert self.runner and self.socket

        return SockSite(
            self.runner, self.socket,
            shutdown_timeout=self.shutdown_timeout,
            ssl_context=await self.loop.run_in_executor(
                None, get_ssl_context, *self.__ssl_options
            ),
        )
