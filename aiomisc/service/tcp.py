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
        self, address: str = None, port: int = None,
        options: OptionsType = (), sock: socket.socket = None, **kwargs: Any
    ):
        if not sock:
            if not (address and port):
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

    def make_client_handler(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Any:
        return self.create_task(awaitable(self.handle_client)(reader, writer))

    async def start(self) -> None:
        self.socket = self.make_socket()
        self.server = await asyncio.start_server(
            self.make_client_handler,
            sock=self.socket,
        )

    async def stop(self, exc: Exception = None) -> None:
        await super().stop(exc)

        if self.server:
            await self.server.wait_closed()


class TCPClient(SimpleClient, ABC):
    PROTO_NAME = "tcp"

    address: str
    port: int
    path: Path

    def __init__(
        self,
        address: str = None,
        port: int = None,
        **kwargs: Any
    ):
        if not (address and port):
            raise RuntimeError('You should pass "address" and "port" couple')
        self.address = address
        self.port = port
        super().__init__(**kwargs)

    async def connect(self) -> Tuple[
        asyncio.StreamReader, asyncio.StreamWriter,
    ]:
        try:
            return await self.create_task(
                asyncio.open_connection(
                    self.address, self.port,
                ),
            )
        finally:
            log.info(
                "Connected to %s://%s:%d",
                self.PROTO_NAME, self.address, self.port,
            )

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
