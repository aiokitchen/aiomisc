import io
import logging
import struct
import asyncio
from time import monotonic

import msgpack

from aiomisc.entrypoint import entrypoint


log = logging.getLogger('client')


class RPCClient:
    HEADER = ">I"
    HEADER_SIZE = struct.calcsize(HEADER)

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter,
                 loop: asyncio.AbstractEventLoop=None):

        self.reader = reader
        self.writer = writer
        self.packer = msgpack.Packer(use_bin_type=True)
        self.unpacker = msgpack.Unpacker(raw=False)
        self.serial = 0
        self.futures = {}
        self.loop = loop or asyncio.get_event_loop()

        self.loop.create_task(self._response_reader())

    async def _response_reader(self):
        try:
            while True:
                body_size = struct.unpack(
                    self.HEADER,
                    await self.reader.readexactly(self.HEADER_SIZE)
                )[0]

                self.unpacker.feed(
                    await self.reader.readexactly(body_size)
                )

                body = self.unpacker.unpack()

                future = self.futures.pop(body['id'], None)

                if future is None:
                    continue

                if 'error' in body:
                    future.set_exception(Exception(
                        body['error']['type'],
                        *body['error']['args']
                    ))
                    continue

                future.set_result(body['result'])
        finally:
            while self.futures:
                _, future = self.futures.popitem()

                if future.done():
                    continue

                future.set_exception(ConnectionAbortedError)

    async def close(self):
        self.writer.write(struct.pack(self.HEADER, 0))
        self.writer.close()
        await self.writer.wait_closed()

    def __call__(self, method, **kwargs):
        self.serial += 1

        self.futures[self.serial] = self.loop.create_future()

        with io.BytesIO() as f:
            body = self.packer.pack({
                'id': self.serial,
                'method': method,
                'params': kwargs,
            })

            f.write(struct.pack(self.HEADER, len(body)))
            f.write(body)

            self.writer.write(f.getvalue())

        return self.futures[self.serial]


async def main(host, port):
    log.info('Connecting to %s:%d', host, port)
    reader, writer = await asyncio.open_connection(host, port)
    client = RPCClient(reader, writer)

    call_count = 300

    delta = - monotonic()

    for i in range(call_count):
        await asyncio.gather(*[
            client('multiply', x=120000, y=1000000) for _ in range(call_count)
        ])

    delta += monotonic()

    total_request_sent = (call_count ** 2)

    log.info("Total executed %d requests on %.3f", total_request_sent, delta)
    log.info("RPS: %.3f", total_request_sent / delta)

    client.close()
    log.info('Close connection')


if __name__ == '__main__':
    with entrypoint() as loop:
        loop.run_until_complete(main("::1", 5678))
