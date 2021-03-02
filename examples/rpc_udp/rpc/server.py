import asyncio
import logging
import struct
import typing
from types import MappingProxyType

import msgspec

from aiomisc.entrypoint import entrypoint
from aiomisc.service import UDPServer
from .spec import Request, Response, Error

log = logging.getLogger()


class RPCServer(UDPServer):
    __required__ = "handlers",

    HEADER = struct.Struct(">I")
    handlers: typing.Dict[str, typing.Callable]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.decoder = msgspec.Decoder(Request)
        self.encoder = msgspec.Encoder()

    async def handle_datagram(self, data: bytes, addr):
        body_bytes = data
        request: Request = self.decoder.decode(body_bytes)

        try:
            response = Response(
                id=request.id,
                result=await self.execute(request.method, request.params)
            )
        except Exception as e:
            response = Response(
                id=request.id,
                error=Error(type=str(type(e)), args=e.args)
            )

        self.sendto(self.encoder.encode(response), addr)

    async def execute(self, method: str, kwargs: dict):
        func = self.handlers[method]

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)


handlers = MappingProxyType({
    "multiply": lambda x, y: x * y,
})


if __name__ == "__main__":
    service = RPCServer(handlers=handlers, address="::", port=15678)

    with entrypoint(service) as loop:
        loop.run_forever()
