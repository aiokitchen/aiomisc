import asyncio
import logging
import socket
from collections import defaultdict
from time import monotonic

import msgpack

from aiomisc.entrypoint import entrypoint


log = logging.getLogger("client")


def get_random_port():
    with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as sock:
        sock.bind(("::1", 0))
        sock.listen()
        return sock.getsockname()[1]


class RPCCallError(RuntimeError):
    pass


class RPCClientUDPProtocol(asyncio.BaseProtocol):
    def __init__(self, loop: asyncio.AbstractEventLoop = None):
        self.loop = loop or asyncio.get_event_loop()
        self.closing = self.loop.create_future()
        self.transport = None
        self.last_id = 1
        self.waiting = defaultdict(dict)
        self.unpacker = msgpack.Unpacker(raw=False)
        self.packer = msgpack.Packer(use_bin_type=True)

    def _get_id(self):
        self.last_id += 1
        return self.last_id

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.unpacker.feed(data)
        payload = self.unpacker.unpack()
        future = self.waiting[addr[:2]][payload["id"]]

        if "error" in payload:
            future.set_exception(RPCCallError(payload["error"], payload))
        else:
            future.set_result(payload["result"])

    def rpc(self, addr, method, **kwargs):
        call_id = self._get_id()
        future = self.loop.create_future()
        self.waiting[addr][call_id] = future

        payload = {
            "id": call_id,
            "method": method,
            "params": kwargs,
        }

        self.transport.sendto(self.packer.pack(payload), addr)
        return future

    def connection_lost(self, exc):
        self.closing.set_exception(exc)


async def main(server_host, server_port, local_host, local_port):
    log.info("Starting reply server at udp://%s:%d", local_host, local_port)
    loop = asyncio.get_event_loop()

    transport, protocol = await loop.create_datagram_endpoint(
        RPCClientUDPProtocol,
        local_addr=(local_host, local_port),
    )

    call_count = 300

    delta = - monotonic()

    for i in range(call_count):
        await asyncio.gather(
            *[
                protocol.rpc(
                    (server_host, server_port),
                    "multiply", x=120000, y=1000000,
                ) for _ in range(call_count)
            ]
        )

    delta += monotonic()

    total_request_sent = (call_count ** 2)

    log.info("Total executed %d requests on %.3f", total_request_sent, delta)
    log.info("RPS: %.3f", total_request_sent / delta)

    log.info("Close connection")


if __name__ == "__main__":
    with entrypoint() as loop:
        loop.run_until_complete(
            main(
                "::1", 15678,
                "::1", get_random_port(),
            ),
        )
