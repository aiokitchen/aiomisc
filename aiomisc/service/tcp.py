import asyncio
import socket

from .base import SimpleServer
from ..utils import OptionsType, bind_socket


class TCPServer(SimpleServer):
    PROTO_NAME = 'tcp'

    def __init__(self, address: str = None, port: int = None,
                 options: OptionsType = (), sock=None):
        if not sock:
            if not (address and port):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                address=address,
                port=port,
                options=options,
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.socket = sock

        super().__init__()

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        raise NotImplementedError

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client,
            sock=self.socket,
            loop=self.loop,
        )

    async def stop(self, exc: Exception = None):
        await super().stop(exc)
        await self.server.wait_closed()
