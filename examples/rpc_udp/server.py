import logging
import struct
import asyncio
from types import MappingProxyType
from typing import Callable, Dict

import msgpack

from aiomisc.entrypoint import entrypoint
from aiomisc.service import UDPServer


log = logging.getLogger()


class RPCServer(UDPServer):
    __required__ = 'handlers',

    HEADER = struct.Struct(">I")
    handlers: Dict[str, Callable]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.unpacker = msgpack.Unpacker(raw=False)
        self.packer = msgpack.Packer(use_bin_type=True)

    async def handle_datagram(self, data: bytes, addr):
        body_bytes = data
        self.unpacker.feed(body_bytes)
        body = self.unpacker.unpack()

        # "method": "subtract", "params": [42, 23], "id": 1}
        req_id = body['id']
        meth = body['method']
        kw = body['params']

        try:
            result = {
                "id": req_id,
                "result": await self.execute(meth, kw)
            }
        except Exception as e:
            result = {
                'id': req_id,
                'error': {'type': str(type(e)), 'args': e.args}
            }

        self.sendto(self.packer.pack(result), addr)

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
    service = RPCServer(handlers=handlers, address='::', port=15678)

    with entrypoint(service) as loop:
        loop.run_forever()
