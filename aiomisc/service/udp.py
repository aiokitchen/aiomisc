import asyncio
import socket
import typing as t
from functools import partial

from ..utils import OptionsType, awaitable, bind_socket
from .base import SimpleServer


_TransportType = t.Optional[asyncio.DatagramTransport]
HandleDatagramType = t.Callable[
    [bytes, tuple], t.Union[t.Awaitable[None], None],
]


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):

        def __init__(
            self, handle_datagram: HandleDatagramType,
            task_factory: t.Callable[..., asyncio.Task],
        ):
            super().__init__()
            self.task_factory = task_factory
            self.handler = awaitable(handle_datagram)
            self.transport = None   # type: _TransportType
            self.loop = None  # type: t.Optional[asyncio.AbstractEventLoop]

        def connection_made(self, transport: t.Any) -> None:
            self.transport = transport
            self.loop = asyncio.get_event_loop()

        def datagram_received(self, data: bytes, addr: tuple) -> None:
            self.task_factory(self.handler(data, addr))

    def __init__(
        self, address: str = None, port: int = None,
        options: OptionsType = (), sock: socket.socket = None,
        **kwargs: t.Any
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

        self._transport = None  # type: t.Optional[asyncio.DatagramTransport]
        self._protocol = None   # type: t.Optional[asyncio.DatagramProtocol]
        self.socket = None      # type: t.Optional[socket.socket]
        super().__init__(**kwargs)

    def sendto(self, data: bytes, addr: tuple) -> t.Any:
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
