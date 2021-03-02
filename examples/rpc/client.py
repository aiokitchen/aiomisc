import io
import logging
import struct
import asyncio
from time import monotonic

import msgspec

from aiomisc.entrypoint import entrypoint

from spec import Request, Response


log = logging.getLogger('client')


class RPCClient:
    HEADER = struct.Struct(">I")

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter,
                 loop: asyncio.AbstractEventLoop = None):

        self.reader = reader
        self.writer = writer
        self.encoder = msgspec.Encoder()
        self.decoder = msgspec.Decoder(Response)
        self.serial = 0
        self.futures = {}
        self.loop = loop or asyncio.get_event_loop()
        self.reader_task = self.loop.create_task(self._response_reader())

    async def _response_reader(self):
        try:
            while True:
                body_size = self.HEADER.unpack(
                    await self.reader.readexactly(self.HEADER.size)
                )[0]

                response = self.decoder.decode(
                    await self.reader.readexactly(body_size)
                )

                future = self.futures.pop(response.id, None)

                if future is None:
                    continue

                if response.error is not None:
                    future.set_exception(Exception(
                        response.error.type,
                        *response.error.args
                    ))
                    continue

                future.set_result(response.result)
        finally:
            while self.futures:
                _, future = self.futures.popitem()

                if future.done():
                    continue

                future.set_exception(ConnectionAbortedError)

    async def close(self):
        self.writer.write(self.HEADER.pack(0))

        self.reader_task.cancel()
        await asyncio.gather(self.reader_task, return_exceptions=True)

        self.loop.call_soon(self.writer.close)
        self.writer.write_eof()
        self.writer.close()

    def __call__(self, method, **kwargs):
        self.serial += 1

        self.futures[self.serial] = self.loop.create_future()

        with io.BytesIO() as f:
            body = self.encoder.encode(
                Request(id=self.serial, method=method, params=kwargs)
            )

            f.write(self.HEADER.pack(len(body)))
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

    await client.close()
    log.info('Close connection')


if __name__ == '__main__':
    with entrypoint() as loop:
        loop.run_until_complete(main("::1", 5678))
