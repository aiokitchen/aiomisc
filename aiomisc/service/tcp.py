import asyncio
import logging
import socket
from abc import ABC, abstractmethod
from functools import partial
from pathlib import Path
from typing import Any, Optional, Tuple

from ..utils import OptionsType, TimeoutType, awaitable, bind_socket
from .base import SimpleClient, SimpleServer


log = logging.getLogger(__name__)


class TCPServer(SimpleServer):
    PROTO_NAME = "tcp"

    def __init__(
        self, address: Optional[str] = None, port: Optional[int] = None,
        options: OptionsType = (), sock: Optional[socket.socket] = None,
        **kwargs: Any,
    ):
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

    @abstractmethod
    async def handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Any:
        raise NotImplementedError

    async def __client_handler(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> Any:
        return await awaitable(self.handle_client)(reader, writer)

    def make_client_handler(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Any:
        return self.create_task(self.__client_handler(reader, writer))

    async def start(self) -> None:
        self.socket = self.make_socket()
        self.server = await asyncio.start_server(
            self.make_client_handler,
            sock=self.socket,
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


class TCPClient(SimpleClient, ABC):
    PROTO_NAME = "tcp"

    address: str
    port: int
    path: Path

    connect_attempts: int = 5
    connect_retry_timeout: TimeoutType = 3

    def __init__(
        self,
        address: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs: Any,
    ):
        if not (address and port):
            raise RuntimeError('You should pass "address" and "port" couple')
        self.address = address
        self.port = port
        super().__init__(**kwargs)

    async def connect(self) -> Tuple[
        asyncio.StreamReader, asyncio.StreamWriter,
    ]:
        last_error: Optional[Exception] = None

        for _ in range(self.connect_attempts):
            try:
                reader, writer = await self.create_task(
                    asyncio.open_connection(
                        self.address, self.port,
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

    @abstractmethod
    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        reader, writer = await self.connect()
        self.loop.call_soon(self.start_event.set)
        try:
            await self.create_task(self.handle_connection(reader, writer))
        except Exception:
            log.exception("Error when handle TCP connection")
        else:
            log.info("Client %r communication has been ended", self)


class RobustTCPClient(TCPClient, ABC):
    reconnect_timeout: TimeoutType = 5
    connected: asyncio.Event

    async def start(self) -> None:
        self.connected = asyncio.Event()

        while True:
            try:
                reader, writer = await self.connect()
                self.connected.set()

                if not self.start_event.is_set():
                    self.start_event.set()

                await self.create_task(self.handle_connection(reader, writer))
                self.connected.clear()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception(
                    "Error when handle TCP connection, "
                    "reconnecting after %.3f seconds",
                    self.reconnect_timeout,
                )
            finally:
                if not self.connected.is_set():
                    return
                await asyncio.sleep(self.reconnect_timeout)
