import asyncio
import socket
from functools import partial
from typing import Any, Awaitable, Callable, Optional, Union

from ..utils import OptionsType, awaitable, bind_socket
from .base import SimpleServer


TransportType = Optional[asyncio.DatagramTransport]
HandleDatagramType = Callable[
    [bytes, tuple], Union[Awaitable[None], None],
]


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):

        def __init__(
            self, handle_datagram: HandleDatagramType,
            task_factory: Callable[..., asyncio.Task],
        ):
            super().__init__()
            self.task_factory = task_factory
            self.handler = awaitable(handle_datagram)
            self.transport: TransportType = None
            self.loop: Optional[asyncio.AbstractEventLoop] = None

        def connection_made(self, transport: Any) -> None:
            self.transport = transport
            self.loop = asyncio.get_event_loop()

        def datagram_received(self, data: bytes, addr: tuple) -> None:
            self.task_factory(self.handler(data, addr))

    def __init__(
        self, address: str = None, port: int = None,
        options: OptionsType = (), sock: socket.socket = None,
        **kwargs: Any
    ):
        if not sock:
            if not (address and port):
                raise RuntimeError(
                    "You should pass socket instance or "
                    '"address" and "port" couple',
                )

            self.make_socket = partial(
                bind_socket,
                socket.AF_INET6 if ":" in address else socket.AF_INET,
                socket.SOCK_DGRAM,
                address=address, port=port, options=options,
                proto_name="udp",
            )

        elif not isinstance(sock, socket.socket):
            raise ValueError("sock must be socket instance")
        else:
            self.make_socket = lambda: sock     # type: ignore

        self._transport: TransportType = None
        self._protocol: Optional[asyncio.DatagramProtocol] = None
        self.socket: Optional[socket.socket] = None
        super().__init__(**kwargs)

    def sendto(self, data: bytes, addr: tuple) -> Any:
        if self._transport is None:
            raise RuntimeError

        return self._transport.sendto(data, addr)

    def handle_datagram(self, data: bytes, addr: tuple) -> None:
        raise NotImplementedError

    async def start(self) -> None:
        self.socket = self.make_socket()

        if self.socket is None or self.loop is None:
            raise RuntimeError

        self._transport, self._protocol = (
            await self.loop.create_datagram_endpoint(   # type: ignore
                lambda: UDPServer.UDPSimpleProtocol(
                    self.handle_datagram,
                    self.create_task,
                ),
                sock=self.socket,
            )
        )

    async def stop(self, exc: Exception = None) -> None:
        await super().stop(exc)
        if self._transport:
            self._transport.close()
