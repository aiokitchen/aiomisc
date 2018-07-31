import asyncio
import socket

from .base import SimpleServer
from ..utils import OptionsType, bind_socket


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):

        def __init__(self, handle_datagram):
            super().__init__()
            self.handler = asyncio.coroutine(handle_datagram)
            self.transport = None  # type: asyncio.DatagramTransport
            self.loop = None  # type: asyncio.AbstractEventLoop

        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport
            self.loop = asyncio.get_event_loop()

        def datagram_received(self, data: bytes, addr: tuple):
            self.loop.create_task(self.handler(data, addr))

    def __init__(self, address: str = None, port: int = None,
                 options: OptionsType = (), sock=None):
        if not sock:
            if not (address and port):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                socket.AF_INET6 if ':' in address else socket.AF_INET,
                socket.SOCK_DGRAM,
                address=address, port=port, options=options,
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.socket = sock

        self.server = None
        self._protocol = None
        super().__init__()

    def handle_datagram(self, data: bytes, addr):
        raise NotImplementedError

    async def start(self):
        self.server, self._protocol = await self.loop.create_datagram_endpoint(
            lambda: UDPServer.UDPSimpleProtocol(self.handle_datagram),
            sock=self.socket,
        )
