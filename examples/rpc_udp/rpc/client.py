import asyncio
import logging
from time import monotonic

from aiomisc.entrypoint import entrypoint

from .server import RPCServer

log = logging.getLogger("client")


async def main(rpc: RPCServer, server_host: str, server_port: int) -> None:
    call_count = 300

    delta = -monotonic()

    for i in range(call_count):
        await asyncio.gather(
            *[
                asyncio.wait_for(
                    rpc(
                        server_host,
                        server_port,
                        "multiply",
                        x=120000,
                        y=1000000,
                    ),
                    timeout=5,
                )
                for _ in range(call_count)
            ]
        )

    delta += monotonic()

    total_request_sent = call_count**2

    log.info("Total executed %d requests on %.3f", total_request_sent, delta)
    log.info("RPS: %.3f", total_request_sent / delta)

    log.info("Close connection")


if __name__ == "__main__":
    service = RPCServer(address="::", port=0, handlers={})
    with entrypoint(service) as loop:
        loop.run_until_complete(main(service, "::1", 15678))
