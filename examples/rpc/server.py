import io
import struct
import asyncio
from types import MappingProxyType

import msgpack

from aiomisc.entrypoint import entrypoint
from aiomisc.service import TCPServer


class RPCServer(TCPServer):
    __required__ = 'handlers',

    HEADER = ">I"
    HEADER_SIZE = struct.calcsize(HEADER)

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):

        unpacker = msgpack.Unpacker(encoding='utf-8')
        packer = msgpack.Packer(use_bin_type=True)

        try:
            while True:
                body_size = struct.unpack(
                    self.HEADER, await reader.readexactly(self.HEADER_SIZE)
                )[0]

                if body_size == 0:
                    return

                body_bytes = await reader.readexactly(body_size)

                unpacker.feed(body_bytes)
                body = unpacker.unpack()

                # "method": "subtract", "params": [42, 23], "id": 1}
                req_id = body['id']
                meth = body['method']
                kw = body['params']

                try:
                    result = {"id": req_id,
                              "result": await self.execute(meth, kw)}
                except Exception as e:
                    result = {
                        'id': req_id,
                        'error': {'type': str(type(e)), 'args': e.args}
                    }

                with io.BytesIO() as f:
                    response = packer.pack(result)
                    f.write(struct.pack(self.HEADER, len(response)))
                    f.write(response)

                    payload = f.getvalue()

                writer.write(payload)
        except Exception as e:
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
