import asyncio
from types import MappingProxyType

from aiomisc.entrypoint import entrypoint
from aiomisc.service import TCPServer

from .spec import RPCBase


class RPCServer(TCPServer, RPCBase):
    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):
        await self.communicate(reader, writer)

    async def start(self) -> None:
        await RPCBase.start(self)
        await TCPServer.start(self)


handlers = MappingProxyType({"multiply": lambda x, y: x * y})


if __name__ == "__main__":
    service = RPCServer(handlers=handlers, address="::", port=5678)

    with entrypoint(service) as loop:
        loop.run_forever()
