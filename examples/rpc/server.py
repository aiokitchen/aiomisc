import io
import logging
import struct
import asyncio
from types import MappingProxyType
from typing import Callable, Dict

import msgpack

from aiomisc.entrypoint import entrypoint
from aiomisc.service import TCPServer


log = logging.getLogger()


class RPCServer(TCPServer):
    __required__ = 'handlers',

    HEADER = struct.Struct(">I")
    handlers: Dict[str, Callable]

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):

        unpacker = msgpack.Unpacker(raw=False)
        packer = msgpack.Packer(use_bin_type=True)

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
                    f.write(self.HEADER.pack(len(response)))
                    f.write(response)

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
