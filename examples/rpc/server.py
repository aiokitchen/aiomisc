import io
import logging
import struct
import asyncio
from types import MappingProxyType
from typing import Callable, Dict

import msgspec

from aiomisc.entrypoint import entrypoint
from aiomisc.service import TCPServer
from spec import Request, Error, Response


log = logging.getLogger()


class RPCServer(TCPServer):
    __required__ = 'handlers',

    HEADER = struct.Struct(">I")
    handlers: Dict[str, Callable]

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):

        decoder = msgspec.Decoder(Request)
        encoder = msgspec.Encoder()

        try:
            while True:
                body_size = self.HEADER.unpack(
                    await reader.readexactly(self.HEADER.size)
                )[0]

                if body_size == 0:
                    log.info('Client tcp://%s:%d initial to close connection',
                             *writer.get_extra_info('peername')[:2])
                    return

                body_bytes = await reader.readexactly(body_size)

                request = decoder.decode(body_bytes)

                try:
                    response = Response(
                        id=request.id,
                        result=await self.execute(
                            request.method, request.params
                        )
                    )
                except Exception as e:
                    response = Response(
                        id=request.id,
                        error=Error(type=str(type(e)), args=e.args)
                    )

                with io.BytesIO() as f:
                    response_bytes = encoder.encode(response)
                    f.write(self.HEADER.pack(len(response_bytes)))
                    f.write(response_bytes)

                    payload = f.getvalue()

                writer.write(payload)
        except Exception:
            writer.close()
            raise

    async def execute(self, method: str, kwargs: dict):
        func = self.handlers[method]

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)


handlers = MappingProxyType({
    'multiply': lambda x, y: x * y,
})


if __name__ == '__main__':
    service = RPCServer(handlers=handlers, address='::', port=5678)

    with entrypoint(service) as loop:
        loop.run_forever()
