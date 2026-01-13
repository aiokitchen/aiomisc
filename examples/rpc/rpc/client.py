import asyncio
import logging
from time import monotonic
from types import MappingProxyType

from aiomisc.entrypoint import entrypoint
from aiomisc.service import RobustTCPClient

from .spec import RPCBase

log = logging.getLogger("client")


class RPCClient(RobustTCPClient, RPCBase):
    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        await self.communicate(reader, writer)

    async def start(self) -> None:
        await RPCBase.start(self)
        await RobustTCPClient.start(self)


async def main(client: RPCClient):
    call_count = 1000

    delta = -monotonic()

    for i in range(call_count):
        await asyncio.gather(
            *[
                client("multiply", x=120000, y=1000000)
                for _ in range(call_count)
            ]
        )

    delta += monotonic()

    total_request_sent = call_count**2

    log.info("Total executed %d requests on %.3f", total_request_sent, delta)
    log.info("RPS: %.3f", total_request_sent / delta)
    log.info("Close connection")


handlers = MappingProxyType({"print": print})


if __name__ == "__main__":
    client = RPCClient("::1", 5678, handlers=handlers)
    with entrypoint(client) as loop:
        loop.run_until_complete(main(client))
