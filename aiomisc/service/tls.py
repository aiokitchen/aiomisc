import asyncio
import socket
import ssl
from functools import partial
from pathlib import Path
from typing import Union

from .base import SimpleServer
from ..utils import OptionsType, bind_socket


PathOrStr = Union[Path, str]


def get_ssl_context(cert, key, ca, verify, require_client_cert):
    cert, key, ca = map(str, (cert, key, ca))

    context = ssl.create_default_context(
        (
            ssl.Purpose.SERVER_AUTH
            if require_client_cert
            else ssl.Purpose.CLIENT_AUTH
        ),
        capath=ca,
    )

    if key:
        context.load_cert_chain(
            cert,
            key,
        )

    if not verify:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

    return context


class TLSServer(SimpleServer):
    PROTO_NAME = 'tls'

    def __init__(self, *, address: str = None, port: int = None,
                 cert: PathOrStr, key: PathOrStr, ca: PathOrStr = None,
                 require_client_cert: bool = False, verify: bool = True,
                 options: OptionsType = (), sock=None, **kwargs):

        self.__ssl_options = cert, key, ca, verify, require_client_cert

        if not sock:
            if not (address and port):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.make_socket = partial(
                bind_socket,
                address=address,
                port=port,
                options=options,
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.make_socket = lambda: sock

        self.socket = None

        super().__init__(**kwargs)

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        raise NotImplementedError

    async def start(self):
        ssl_context = await self.loop.run_in_executor(
            None, get_ssl_context, *self.__ssl_options
        )

        self.socket = self.make_socket()

        self.server = await asyncio.start_server(
            self.handle_client,
            sock=self.socket,
            loop=self.loop,
            ssl=ssl_context
        )

    async def stop(self, exc: Exception = None):
        await super().stop(exc)
        await self.server.wait_closed()
