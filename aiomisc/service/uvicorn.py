import abc
import asyncio
import logging
import os
import socket
import ssl
from typing import Any, Awaitable, Callable, List, Optional, Tuple, Type, Union

from asgiref.typing import ASGIApplication
from uvicorn.config import (
    SSL_PROTOCOL_VERSION, Config, HTTPProtocolType, InterfaceType, LifespanType,
    WSProtocolType,
)
from uvicorn.server import Server

from aiomisc.service import Service


log = logging.getLogger(__name__)

UvicornApplication = Union[ASGIApplication, Callable]


class UvicornService(Service, abc.ABC):
    __async_required__: Tuple[str, ...] = (
        "start",
        "stop",
        "create_application",
    )

    sock: Optional[socket.socket] = None

    host: str = "127.0.0.1"
    port: int = 8080
    uds: Optional[str] = None
    fd: Optional[int] = None
    http: Union[Type[asyncio.Protocol], HTTPProtocolType] = "auto"
    ws: Union[Type[asyncio.Protocol], WSProtocolType] = "auto"
    ws_max_size: int = 16 * 1024 * 1024
    ws_ping_interval: Optional[float] = 20.0
    ws_ping_timeout: Optional[float] = 20.0
    ws_per_message_deflate: bool = True
    lifespan: LifespanType = "auto"
    access_log: bool = True
    interface: InterfaceType = "auto"
    proxy_headers: bool = True
    server_header: bool = True
    date_header: bool = True
    forwarded_allow_ips: Optional[Union[List[str], str]] = None
    root_path: str = ""
    limit_concurrency: Optional[int] = None
    limit_max_requests: Optional[int] = None
    backlog: int = 2048
    timeout_keep_alive: int = 5
    timeout_notify: int = 30
    timeout_graceful_shutdown: Optional[int] = None
    callback_notify: Optional[Callable[..., Awaitable[None]]] = None
    ssl_keyfile: Optional[str] = None
    ssl_certfile: Optional[Union[str, os.PathLike]] = None
    ssl_keyfile_password: Optional[str] = None
    ssl_version: int = SSL_PROTOCOL_VERSION
    ssl_cert_reqs: int = ssl.CERT_NONE
    ssl_ca_certs: Optional[str] = None
    ssl_ciphers: str = "TLSv1"
    headers: Optional[List[Tuple[str, str]]] = None
    factory: bool = False
    h11_max_incomplete_event_size: Optional[int] = None

    @abc.abstractmethod
    async def create_application(self) -> UvicornApplication:
        raise NotImplementedError

    async def start(self) -> Any:
        app = await self.create_application()

        config = Config(
            app,
            host=self.host,
            port=self.port,
            uds=self.uds,
            fd=self.fd,
            http=self.http,
            ws=self.ws,
            ws_max_size=self.ws_max_size,
            ws_ping_interval=self.ws_ping_interval,
            ws_ping_timeout=self.ws_ping_timeout,
            ws_per_message_deflate=self.ws_per_message_deflate,
            lifespan=self.lifespan,
            access_log=self.access_log,
            interface=self.interface,
            proxy_headers=self.proxy_headers,
            server_header=self.server_header,
            date_header=self.date_header,
            forwarded_allow_ips=self.forwarded_allow_ips,
            root_path=self.root_path,
            limit_concurrency=self.limit_concurrency,
            limit_max_requests=self.limit_max_requests,
            backlog=self.backlog,
            timeout_keep_alive=self.timeout_keep_alive,
            timeout_notify=self.timeout_notify,
            timeout_graceful_shutdown=self.timeout_graceful_shutdown,
            callback_notify=self.callback_notify,
            ssl_keyfile=self.ssl_keyfile,
            ssl_certfile=self.ssl_certfile,
            ssl_keyfile_password=self.ssl_keyfile_password,
            ssl_version=self.ssl_version,
            ssl_cert_reqs=self.ssl_cert_reqs,
            ssl_ca_certs=self.ssl_ca_certs,
            ssl_ciphers=self.ssl_ciphers,
            headers=self.headers,
            factory=self.factory,
            h11_max_incomplete_event_size=self.h11_max_incomplete_event_size,
            log_config=None,
            use_colors=False,
        )
        if not self.sock:
            self.sock = config.bind_socket()
        self.server = Server(config)
        self.serve_task = asyncio.create_task(
            self.server.serve(sockets=[self.sock])
        )

    async def stop(self, exception: Optional[Exception] = None) -> None:
        self.server.should_exit = True
        await self.serve_task
