import asyncio
import logging
import socket
import ssl
from abc import ABC, abstractmethod
from functools import partial
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from ..utils import OptionsType, TimeoutType, awaitable, bind_socket
from .base import SimpleServer
from .tcp import RobustTCPClient, TCPClient


PathOrStr = Union[Path, str]
log = logging.getLogger(__name__)


def get_ssl_context(
    cert: str, key: str, ca: Optional[str], verify: bool,
    require_client_cert: bool, purpose: ssl.Purpose,
) -> ssl.SSLContext:
    cert, key, ca = map(str, (cert, key, ca))

    context = ssl.create_default_context(purpose=purpose, cafile=ca)

    if ca and not Path(ca).exists():
        raise FileNotFoundError("CA file doesn't exists")

    if require_client_cert:
        context.verify_mode = ssl.VerifyMode.CERT_REQUIRED

    if key:
        context.load_cert_chain(
            cert,
            key,
        )

    if not verify:
        context.check_hostname = False

    return context


class TLSServer(SimpleServer):
    PROTO_NAME = "tls"

    def __init__(
        self, *, address: Optional[str] = None, port: Optional[int] = None,
        cert: PathOrStr, key: PathOrStr, ca: Optional[PathOrStr] = None,
        require_client_cert: bool = False, verify: bool = True,
        options: OptionsType = (), sock: Optional[socket.socket] = None,
        **kwargs: Any,
    ):

        self.__ssl_options = (
            cert, key, ca, verify, require_client_cert,
            ssl.Purpose.CLIENT_AUTH,
        )

        if not sock:
            if address is None or port is None:
                raise RuntimeError(
                    "You should pass socket instance or "
                    '"address" and "port" couple',
                )

            self.make_socket = partial(
                bind_socket,
                address=address,
                port=port,
                options=options,
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError("sock must be socket instance")
        else:
            self.make_socket = lambda: sock     # type: ignore

        self.socket: Optional[socket.socket] = None

        super().__init__(**kwargs)

    async def __client_handler(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> Any:
        return await awaitable(self.handle_client)(reader, writer)

    def make_client_handler(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> asyncio.Task:
        return self.create_task(self.__client_handler(reader, writer))

    @abstractmethod
    async def handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Any:
        raise NotImplementedError

    async def start(self) -> None:
        ssl_context = await self.loop.run_in_executor(
            None, get_ssl_context, *self.__ssl_options,
        )

        self.socket = self.make_socket()

        self.server = await asyncio.start_server(
            self.make_client_handler,
            sock=self.socket,
            ssl=ssl_context,
        )

    async def stop(self, exc: Optional[Exception] = None) -> None:
        await super().stop(exc)

        if self.server:
            await self.server.wait_closed()

    @property
    def __sockname(self) -> Optional[tuple]:
        if self.socket:
            return self.socket.getsockname()
        return None

    @property
    def address(self) -> Optional[str]:
        if self.__sockname:
            return self.__sockname[0]
        return None

    @property
    def port(self) -> Optional[int]:
        if self.__sockname:
            return self.__sockname[1]
        return None


class TLSClient(TCPClient, ABC):
    __slots__ = "__ssl_options", "__server_hostname"

    connect_attempts: int = 5
    connect_retry_timeout: TimeoutType = 3

    def __init__(
        self, address: str, port: int, *,
        cert: PathOrStr, key: PathOrStr,
        ca: Optional[PathOrStr] = None, verify: bool = True,
        **kwargs: Any,
    ) -> None:
        self.__ssl_options = (
            cert, key, ca, verify, False, ssl.Purpose.SERVER_AUTH,
        )

        super().__init__(address, port, **kwargs)

    async def connect(self) -> Tuple[
        asyncio.StreamReader, asyncio.StreamWriter,
    ]:
        last_error: Optional[Exception] = None
        for _ in range(self.connect_attempts):
            try:
                reader, writer = await asyncio.open_connection(
                    self.address, self.port,
                    ssl=await self.loop.run_in_executor(
                        None, get_ssl_context, *self.__ssl_options,
                    ),
                )
                log.info(
                    "Connected to %s://%s:%d",
                    self.PROTO_NAME, self.address, self.port,
                )
                return reader, writer
            except ConnectionError as e:
                last_error = e
                await asyncio.sleep(self.connect_retry_timeout)

        raise last_error or RuntimeError("Unknown exception occurred")


class RobustTLSClient(RobustTCPClient, ABC):
    __slots__ = "__ssl_options", "__server_hostname"

    connect_attempts: int = 5
    connect_retry_timeout: TimeoutType = 3

    def __init__(
        self, address: str, port: int, *,
        cert: PathOrStr, key: PathOrStr,
        ca: Optional[PathOrStr] = None, verify: bool = True,
        **kwargs: Any,
    ):
        self.__ssl_options = (
            cert, key, ca, verify, False, ssl.Purpose.SERVER_AUTH,
        )

        super().__init__(address, port, **kwargs)

    async def connect(self) -> Tuple[
        asyncio.StreamReader, asyncio.StreamWriter,
    ]:
        last_error: Optional[Exception] = None
        for _ in range(self.connect_attempts):
            try:
                reader, writer = await asyncio.open_connection(
                    self.address, self.port,
                    ssl=await self.loop.run_in_executor(
                        None, get_ssl_context, *self.__ssl_options,
                    ),
                )
                log.info(
                    "Connected to %s://%s:%d",
                    self.PROTO_NAME, self.address, self.port,
                )
                return reader, writer
            except ConnectionError as e:
                last_error = e
                await asyncio.sleep(self.connect_retry_timeout)

        raise last_error or RuntimeError("Unknown exception occurred")
