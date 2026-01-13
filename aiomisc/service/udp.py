import asyncio
import socket
from abc import abstractmethod
from collections.abc import Awaitable, Callable
from functools import partial
from typing import Any

from ..utils import OptionsType, awaitable, bind_socket
from .base import SimpleServer

TransportType = asyncio.DatagramTransport | None
HandleDatagramType = Callable[[bytes, tuple], Awaitable[None] | None]


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):
        def __init__(
            self,
            handle_datagram: HandleDatagramType,
            task_factory: Callable[..., asyncio.Task],
        ):
            super().__init__()
            self.task_factory = task_factory
            self.handler = awaitable(handle_datagram)
            self.transport: TransportType = None
            self.loop: asyncio.AbstractEventLoop | None = None

        def connection_made(self, transport: Any) -> None:
            self.transport = transport
            self.loop = asyncio.get_running_loop()

        def datagram_received(self, data: bytes, addr: tuple) -> None:
            self.task_factory(self.handler(data, addr))

    def __init__(
        self,
        address: str | None = None,
        port: int | None = None,
        options: OptionsType = (),
        sock: socket.socket | None = None,
        **kwargs: Any,
    ):
        if not sock:
            if address is None or port is None:
                raise RuntimeError(
                    "You should pass socket instance or "
                    '"address" and "port" couple'
                )

            self.make_socket = partial(
                bind_socket,
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_DGRAM,
                address=address,
                port=port,
                options=options,
                proto_name="udp",
            )

        elif not isinstance(sock, socket.socket):
            raise ValueError("sock must be socket instance")
        else:
            self.make_socket = lambda: sock  # type: ignore

        self._transport: TransportType = None
        self._protocol: asyncio.DatagramProtocol | None = None
        self.socket: socket.socket | None = None
        super().__init__(**kwargs)

    def sendto(self, data: bytes, addr: tuple) -> Any:
        if self._transport is None:
            raise RuntimeError

        return self._transport.sendto(data, addr)

    @abstractmethod
    async def handle_datagram(self, data: bytes, addr: tuple) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        self.socket = self.make_socket()

        if self.socket is None or self.loop is None:
            raise RuntimeError

        (
            self._transport,
            self._protocol,
        ) = await self.loop.create_datagram_endpoint(
            lambda: UDPServer.UDPSimpleProtocol(
                self.handle_datagram, self.create_task
            ),
            sock=self.socket,
        )

    @property
    def __sockname(self) -> tuple | None:
        if self._transport:
            return self._transport.get_extra_info("sockname")
        return None

    @property
    def address(self) -> str | None:
        if self.__sockname:
            return self.__sockname[0]
        return None

    @property
    def port(self) -> int | None:
        if self.__sockname:
            return self.__sockname[1]
        return None

    async def stop(self, exc: Exception | None = None) -> None:
        await super().stop(exc)
        if self._transport:
            self._transport.close()
