import asyncio
import socket
from functools import partial

from ..utils import OptionsType, awaitable, bind_socket
from .base import SimpleServer


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):

        def __init__(self, handle_datagram, task_factory):
            super().__init__()
            self.task_factory = task_factory
            self.handler = awaitable(handle_datagram)
            self.transport = None   # type: asyncio.DatagramTransport
            self.loop = None        # type: asyncio.AbstractEventLoop

        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport
            self.loop = asyncio.get_event_loop()

        def datagram_received(self, data: bytes, addr: tuple):
            self.task_factory(self.handler(data, addr))

    def __init__(
        self, address: str = None, port: int = None,
        options: OptionsType = (), sock=None, **kwargs
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
            self.make_socket = lambda: sock

        self.server = None
        self._protocol = None
        self.socket = None
        super().__init__(**kwargs)

    def sendto(self, data, addr):
        return self._protocol.transport.sendto(data, addr)

    def handle_datagram(self, data: bytes, addr):
        raise NotImplementedError

    async def start(self):
        self.socket = self.make_socket()

        self.server, self._protocol = await self.loop.create_datagram_endpoint(
            lambda: UDPServer.UDPSimpleProtocol(
                self.handle_datagram,
                self.create_task,
            ),
            sock=self.socket,
        )
