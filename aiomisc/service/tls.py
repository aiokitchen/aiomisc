import asyncio
import logging
import socket
import ssl
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Optional, Tuple, Union

from ..utils import OptionsType, TimeoutType, awaitable, bind_socket
from .base import SimpleServer
from .tcp import RobustTCPClient, TCPClient


PathOrStr = Union[Path, str]
log = logging.getLogger(__name__)


DEFAULT_SSL_CIPHERS = (
    "ECDHE-RSA-AES256-GCM-SHA384",
    "ECDHE-ECDSA-AES256-GCM-SHA384",
    "ECDHE-RSA-CHACHA20-POLY1305",
    "ECDHE-ECDSA-CHACHA20-POLY1305",
    "ECDHE-RSA-AES128-GCM-SHA256",
    "ECDHE-ECDSA-AES128-GCM-SHA256",
)

DEFAULT_SSL_MIN_VERSION = ssl.TLSVersion.TLSv1_3
DEFAULT_SSL_MAX_VERSION = ssl.TLSVersion.TLSv1_3


@dataclass(frozen=True)
class SSLOptionsBase:
    cert: Optional[Path]
    key: Optional[Path]
    ca: Optional[Path]
    verify: bool
    require_client_cert: bool
    purpose: ssl.Purpose
    minimum_version: ssl.TLSVersion = DEFAULT_SSL_MIN_VERSION
    maximum_version: ssl.TLSVersion = DEFAULT_SSL_MAX_VERSION
    ciphers: Tuple[str, ...] = DEFAULT_SSL_CIPHERS


class SSLOptions(SSLOptionsBase):
    def __init__(
        self, cert: Optional[PathOrStr], key: Optional[PathOrStr],
        ca: Optional[PathOrStr], verify: bool, require_client_cert: bool,
        purpose: ssl.Purpose,
        minimum_version: ssl.TLSVersion = DEFAULT_SSL_MIN_VERSION,
        maximum_version: ssl.TLSVersion = DEFAULT_SSL_MAX_VERSION,
        ciphers: Tuple[str, ...] = DEFAULT_SSL_CIPHERS,
    ) -> None:
        super().__init__(
            cert=Path(cert) if cert else None,
            key=Path(key) if key else None,
            ca=Path(ca) if ca else None,
            verify=verify,
            require_client_cert=require_client_cert,
            purpose=purpose,
            minimum_version=minimum_version,
            maximum_version=maximum_version,
            ciphers=ciphers,
        )

    def create_context(self) -> ssl.SSLContext:
        context = ssl.create_default_context(
            purpose=self.purpose,
        )

        # Disable compression to prevent CRIME attacks
        context.options |= ssl.OP_NO_COMPRESSION

        context.maximum_version = self.maximum_version
        context.minimum_version = self.minimum_version
        context.set_ciphers(":".join(self.ciphers))

        if not self.verify:
            context.check_hostname = False

        if self.ca:
            log.debug("Loading CA from %s", self.ca)
            if not self.ca.exists():
                raise FileNotFoundError(
                    "CA file doesn't exists", str(self.ca.resolve()),
                )
            context.load_verify_locations(cafile=str(self.ca))

        if self.require_client_cert:
            log.debug("Set server-side cert verification")
            context.verify_mode = ssl.VerifyMode.CERT_REQUIRED
            # Post-handshake authentication is required
            context.post_handshake_auth = True
        else:
            # Disable server-side cert verification
            context.check_hostname = False
            context.verify_mode = ssl.VerifyMode.CERT_NONE

        # Load server-side cert and key
        if self.key and self.cert:
            context.load_cert_chain(self.cert, self.key)

        return context


class TLSServer(SimpleServer):
    PROTO_NAME = "tls"

    def __init__(
        self, *, address: Optional[str] = None, port: Optional[int] = None,
        cert: PathOrStr, key: PathOrStr, ca: Optional[PathOrStr] = None,
        require_client_cert: bool = False, verify: bool = True,
        minimum_version: ssl.TLSVersion = DEFAULT_SSL_MIN_VERSION,
        maximum_version: ssl.TLSVersion = DEFAULT_SSL_MAX_VERSION,
        ciphers: Tuple[str, ...] = DEFAULT_SSL_CIPHERS,
        options: OptionsType = (), sock: Optional[socket.socket] = None,
        **kwargs: Any,
    ):

        self.__ssl_options = SSLOptions(
            cert=cert, key=key, ca=ca, verify=verify,
            require_client_cert=require_client_cert,
            purpose=ssl.Purpose.CLIENT_AUTH,
            minimum_version=minimum_version,
            maximum_version=maximum_version,
            ciphers=ciphers,
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
            None, self.__ssl_options.create_context,
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
        self.__ssl_options = SSLOptions(
            cert, key, ca, verify, False, ssl.Purpose.SERVER_AUTH,
        )

        super().__init__(address, port, **kwargs)

    async def connect(self) -> Tuple[
        asyncio.StreamReader, asyncio.StreamWriter,
    ]:
        last_error: Optional[Exception] = None
        for _ in range(self.connect_attempts):
            try:
                ssl_context: ssl.SSLContext = await self.loop.run_in_executor(
                    None, self.__ssl_options.create_context,
                )
                reader, writer = await asyncio.open_connection(
                    self.address, self.port,
                    ssl=ssl_context,
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
        self.__ssl_options = SSLOptions(
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
                        None, self.__ssl_options.create_context,
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
