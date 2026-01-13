import asyncio
import logging
import struct
import typing
from types import MappingProxyType

import msgspec

from aiomisc.entrypoint import entrypoint
from aiomisc.service import UDPServer

from .spec import Error, Payload, Request, Response

log = logging.getLogger()


class RPCCallError(RuntimeError):
    pass


class RPCServer(UDPServer):
    __required__ = ("handlers",)

    HEADER = struct.Struct(">I")
    handlers: dict[str, typing.Callable]

    _serial: int
    _encoder: msgspec.msgpack.Encoder
    _decoder: msgspec.msgpack.Decoder
    _futures: typing.MutableMapping[int, asyncio.Future]

    async def start(self) -> None:
        self._serial: int = 0
        self._futures = {}
        self._decoder = msgspec.msgpack.Decoder(Payload)
        self._encoder = msgspec.msgpack.Encoder()
        await super().start()

    async def execute(self, method: str, kwargs: dict):
        func = self.handlers[method]

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        else:
            return func(**kwargs)

    async def _on_request(self, request: Request, addr: tuple) -> typing.Any:
        try:
            response = Response(
                id=request.id,
                result=await self.execute(request.method, request.params),
            )
        except Exception as e:
            response = Response(
                id=request.id, error=Error(type=str(type(e)), args=e.args)
            )

        self.sendto(self._encoder.encode(Payload(response=response)), addr)

    def _on_response(self, response: Response) -> typing.Any:
        future: asyncio.Future = self._futures.pop(response.id)
        if not future.done():
            if response.result is not None:
                future.set_result(response.result)
                return

            future.set_exception(
                RPCCallError(response.error.type, response.error.args)
            )

    async def handle_datagram(self, data: bytes, addr):
        body_bytes = data
        payload: Payload = self._decoder.decode(body_bytes)

        if payload.request is not None:
            self.create_task(self._on_request(payload.request, addr))
        elif payload.response is not None:
            self._on_response(payload.response)

    def __call__(
        self, host: str, port: int, method: str, **params: typing.Any
    ) -> typing.Any:
        self._serial += 1
        serial = self._serial
        future = self.loop.create_future()
        request: bytes = self._encoder.encode(
            Payload(request=Request(id=serial, method=method, params=params))
        )
        self._futures[serial] = future
        self.sendto(request, (host, port))
        return future


handlers = MappingProxyType({"multiply": lambda x, y: x * y})


if __name__ == "__main__":
    service = RPCServer(handlers=handlers, address="::", port=15678)

    with entrypoint(service) as loop:
        loop.run_forever()
