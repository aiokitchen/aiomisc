import socket
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Union

from aiohttp.web import Application, AppRunner, BaseRunner, SockSite  # noqa

from aiomisc.service.tls import PathOrStr, get_ssl_context

from ..utils import bind_socket
from .base import Service


try:
    from aiohttp.web_log import AccessLogger
except ImportError:         # pragma: nocover
    from aiohttp.helpers import AccessLogger  # type: ignore


RunnerKwargsType = Union[Mapping[str, Any], Iterable[Tuple[str, Any]]]


class AIOHTTPService(Service):
    __async_required__: Tuple[str, ...] = (
        "start", "create_application",
    )

    site: SockSite
    runner: BaseRunner

    def __init__(
        self, address: Optional[str] = "localhost", port: Optional[int] = None,
        sock: Optional[socket.socket] = None, shutdown_timeout: int = 5,
        runner_kwargs: Optional[RunnerKwargsType] = None,
        **kwds: Any,
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

        self.shutdown_timeout = shutdown_timeout

        self.runner_kwargs: Dict[str, Any] = dict(runner_kwargs or {})
        self.runner_kwargs.setdefault("access_log_class", AccessLogger)
        self.runner_kwargs.setdefault(
            "access_log_format", AccessLogger.LOG_FORMAT,
        )

        super().__init__(**kwds)

    async def create_application(self) -> Application:
        return Application()

    async def create_site(self) -> SockSite:
        if getattr(self, "runner", None) is None:
            raise RuntimeError("runner already created")

        return SockSite(
            self.runner, self.socket,
            shutdown_timeout=self.shutdown_timeout,
        )

    async def make_runner(self, application: Application) -> AppRunner:
        return AppRunner(
            application,
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

    async def stop(self, exception: Optional[Exception] = None) -> None:
        try:
            if self.site:
                await self.site.stop()
        finally:
            if hasattr(self, "runner"):
                await self.runner.cleanup()


class AIOHTTPSSLService(AIOHTTPService):
    def __init__(
        self, cert: PathOrStr, key: PathOrStr, ca: Optional[PathOrStr] = None,
        address: Optional[str] = None, port: Optional[int] = None,
        verify: bool = True, sock: Optional[socket.socket] = None,
        shutdown_timeout: int = 5, require_client_cert: bool = False,
        **kwds: Any,
    ):

        super().__init__(
            address=address, port=port, sock=sock,
            shutdown_timeout=shutdown_timeout, **kwds,
        )

        self.__ssl_options = cert, key, ca, verify, require_client_cert

    async def create_site(self) -> SockSite:
        assert self.runner and self.socket

        return SockSite(
            self.runner, self.socket,
            shutdown_timeout=self.shutdown_timeout,
            ssl_context=await self.loop.run_in_executor(
                None, get_ssl_context, *self.__ssl_options,
            ),
        )
