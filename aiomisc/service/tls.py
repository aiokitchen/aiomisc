import asyncio
import socket
import ssl
from functools import partial
from pathlib import Path
from typing import Any, Optional, Union

from ..utils import OptionsType, awaitable, bind_socket
from .base import SimpleServer


PathOrStr = Union[Path, str]


def get_ssl_context(
    cert: str, key: str, ca: Optional[str], verify: bool,
    require_client_cert: bool,
) -> ssl.SSLContext:
    cert, key, ca = map(str, (cert, key, ca))

    context = ssl.create_default_context(
        ssl.Purpose.CLIENT_AUTH,
        cafile=ca,
    )

    if ca and not Path(ca).exists():
        raise FileNotFoundError("CA file doesn't exists")

    if require_client_cert:
        context.verify_mode = ssl.VerifyMode.CERT_REQUIRED

    if key:
        context.load_cert_chain(
            cert,
            key,
        )

    if not verify:
        context.check_hostname = False

    return context


class TLSServer(SimpleServer):
    PROTO_NAME = "tls"

    def __init__(
        self, *, address: str = None, port: int = None,
        cert: PathOrStr, key: PathOrStr, ca: PathOrStr = None,
        require_client_cert: bool = False, verify: bool = True,
        options: OptionsType = (), sock: socket.socket = None, **kwargs: Any
    ):

        self.__ssl_options = cert, key, ca, verify, require_client_cert

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

    def make_client_handler(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> asyncio.Task:
        return self.create_task(awaitable(self.handle_client)(reader, writer))

    async def handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> Any:
        raise NotImplementedError

    async def start(self) -> None:
        ssl_context = await self.loop.run_in_executor(
            None, get_ssl_context, *self.__ssl_options
        )

        self.socket = self.make_socket()

        self.server = await asyncio.start_server(
            self.make_client_handler,
            sock=self.socket,
            ssl=ssl_context,
        )

    async def stop(self, exc: Exception = None) -> None:
        await super().stop(exc)

        if self.server:
            await self.server.wait_closed()
