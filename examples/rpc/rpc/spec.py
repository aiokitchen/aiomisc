import logging
import struct
from asyncio import (
    Future,
    IncompleteReadError,
    Lock,
    Queue,
    StreamReader,
    StreamWriter,
    iscoroutinefunction,
)
from io import BytesIO
from typing import Any, Dict, Optional
from collections.abc import AsyncIterable, Callable, Mapping, MutableMapping

import msgspec

from aiomisc import cancel_tasks
from aiomisc.service.base import TaskStoreBase

log = logging.getLogger()


class Request(msgspec.Struct):
    id: int
    method: str
    params: dict[str, Any]


class Error(msgspec.Struct):
    type: str
    args: Any


class Response(msgspec.Struct):
    id: int
    result: Any | None = None
    error: Error | None = None


class Payload(msgspec.Struct):
    request: Request | None = None
    response: Response | None = None


class Protocol:
    PACKET_HEADER = struct.Struct(">I")
    reader: StreamReader
    writer: StreamWriter

    def __init__(self, reader: StreamReader, writer: StreamWriter):
        self.reader = reader
        self.writer = writer
        self.encoder = msgspec.msgpack.Encoder()
        self.decoder = msgspec.msgpack.Decoder(Payload)
        self.write_lock = Lock()

    def __aiter__(self) -> AsyncIterable[Payload]:
        return self

    async def __anext__(self) -> Payload:
        if self.reader.at_eof():
            raise StopAsyncIteration()

        try:
            payload_size: int = self.PACKET_HEADER.unpack(
                await self.reader.readexactly(self.PACKET_HEADER.size)
            )[0]
            payload_bytes: bytes = await self.reader.readexactly(payload_size)
            return self.decoder.decode(payload_bytes)
        except IncompleteReadError:
            raise StopAsyncIteration()

    async def send(self, payload: Payload) -> None:
        payload_bytes: bytes = self.encoder.encode(payload)
        with BytesIO() as fp:
            fp.write(self.PACKET_HEADER.pack(len(payload_bytes)))
            fp.write(payload_bytes)
            packet = fp.getvalue()

        async with self.write_lock:
            self.writer.write(packet)


class RPCBase(TaskStoreBase):
    __required__ = ("handlers",)

    _futures: MutableMapping[int, Future]
    _serial: int
    _request_queue: Queue
    handlers: Mapping[str, Callable]

    async def start(self) -> None:
        self._futures = {}
        self._serial = 0
        self._request_queue = Queue()

    def _on_response(self, response: Response) -> None:
        future = self._futures.pop(response.id, None)

        if future.done():
            return

        if response.error is not None:
            future.set_exception(
                Exception(response.error.type, *response.error.args)
            )
            return
        future.set_result(response.result)

    async def execute(self, protocol: Protocol, request: Request):
        try:
            func = self.handlers[request.method]
            if iscoroutinefunction(func):
                result = await func(**request.params)
            else:
                result = func(**request.params)
            payload = Payload(response=Response(id=request.id, result=result))
        except Exception as e:
            log.exception("Execution error:")
            payload = Payload(
                response=Response(
                    id=request.id, error=Error(type=str(type(e)), args=e.args)
                )
            )
        await protocol.send(payload)

    async def _request_writer(self, protocol: Protocol) -> None:
        while True:
            payload: Payload = await self._request_queue.get()
            await protocol.send(payload)

    def __call__(self, method, **kwargs):
        self._serial += 1
        future = self.loop.create_future()
        self._futures[self._serial] = future
        self._request_queue.put_nowait(
            Payload(
                request=Request(id=self._serial, method=method, params=kwargs)
            )
        )
        return self._futures[self._serial]

    async def communicate(self, reader: StreamReader, writer: StreamWriter):
        protocol = Protocol(reader, writer)
        request_writer_task = self.create_task(self._request_writer(protocol))

        client_host, client_port = writer.get_extra_info("peername")[:2]
        if ":" in client_host:
            client_host = f"[{client_host}]"

        log.info(
            "Start communication with tcp://%s:%d", client_host, client_port
        )

        # noinspection PyBroadException
        try:
            async for payload in protocol:
                if payload.request is not None:
                    self.create_task(self.execute(protocol, payload.request))
                if payload.response is not None:
                    self._on_response(payload.response)
        except Exception:
            log.exception(
                "Error when communication tcp://%s:%d/",
                client_host,
                client_port,
            )
        finally:
            if writer.can_write_eof():
                writer.write_eof()
            writer.close()
            log.info(
                "Communication with tcp://%s:%d finished",
                client_host,
                client_port,
            )

            await cancel_tasks([request_writer_task])
            await writer.wait_closed()
