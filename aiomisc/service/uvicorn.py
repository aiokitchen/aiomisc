import abc
import asyncio
import logging
import os
import signal
import socket
from typing import (
    Any, Awaitable, Callable, List, Optional, Tuple, Type, Union, cast,
)

from asgiref.typing import ASGIApplication
from uvicorn.server import Server
from uvicorn.config import (
    HTTPProtocolType, InterfaceType, LifespanType, LoopSetupType,
    WSProtocolType, Config
)

from aiomisc.compat import TypedDict
from aiomisc.service import Service


log = logging.getLogger(__name__)

UvicornApplication = Union[ASGIApplication, Callable]


class ConfigKwargs(TypedDict, total=False):
    host: str
    port: int
    uds: Optional[str]
    fd: Optional[int]
    loop: LoopSetupType
    http: Union[Type[asyncio.Protocol], HTTPProtocolType]
    ws: Union[Type[asyncio.Protocol], WSProtocolType]
    ws_max_size: int
    ws_ping_interval: Optional[float]
    ws_ping_timeout: Optional[float]
    ws_per_message_deflate: bool
    lifespan: LifespanType
    access_log: bool
    interface: InterfaceType
    proxy_headers: bool
    server_header: bool
    date_header: bool
    forwarded_allow_ips: Optional[Union[List[str], str]]
    root_path: str
    limit_concurrency: Optional[int]
    limit_max_requests: Optional[int]
    backlog: int
    timeout_keep_alive: int
    timeout_notify: int
    timeout_graceful_shutdown: Optional[int]
    callback_notify: Optional[Callable[..., Awaitable[None]]]
    ssl_keyfile: Optional[str]
    ssl_certfile: Optional[Union[str, os.PathLike]]
    ssl_keyfile_password: Optional[str]
    ssl_version: int
    ssl_cert_reqs: int
    ssl_ca_certs: Optional[str]
    ssl_ciphers: str
    headers: Optional[List[Tuple[str, str]]]
    h11_max_incomplete_event_size: Optional[int]


class UvicornService(Service, abc.ABC):
    __async_required__: Tuple[str, ...] = (
        "start",
        "create_application",
    )

    sock: Optional[socket.socket] = None

    server: Server
    runner: Optional[asyncio.Task] = None

    def __init__(
        self,
        sock: Optional[socket.socket] = None,
        config_kwargs: Optional[ConfigKwargs] = None,
        **kwargs: Any,
    ):
        self.sock = sock

        config_kwargs = cast(ConfigKwargs, dict(config_kwargs or dict()))
        config_kwargs.setdefault("access_log", True)
        config_kwargs.setdefault("host", "127.0.0.1")
        config_kwargs.setdefault("port", 8080)

        self.config_kwargs = config_kwargs
        super().__init__(**kwargs)

    @abc.abstractmethod
    async def create_application(self) -> UvicornApplication:
        raise NotImplementedError

    async def start(self) -> Any:
        app = await self.create_application()

        config = Config(
            app,
            log_config=None,
            use_colors=False,
            **self.config_kwargs,
        )
        if not self.sock:
            self.sock = config.bind_socket()
        self.server = Server(config)
        self.runner = asyncio.create_task(
            self.server.serve(sockets=[self.sock])
        )
        return None

    async def stop(self, exception: Optional[Exception] = None) -> Any:
        if not self.runner:
            return
        try:
            self.server.handle_exit(signal.SIGINT, frame=None)
            await self.runner
        except Exception:
            log.error("Cannot graceful shutdown serve task")
            self.runner.cancel()
        return await super().stop(exception)
