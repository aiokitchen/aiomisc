import asyncio
import io
import pickle
import platform
import socket
from abc import ABC, abstractmethod
from struct import Struct
from typing import IO, Any, BinaryIO, Union


ADDRESS_FAMILY = (
    socket.AF_INET6 if platform.system() == "Windows" else socket.AF_UNIX
)


class Protocol(ABC):
    PACKET_HEADER = Struct("!L")

    @abstractmethod
    def _read(self, size: int) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def _write(self, data: bytes) -> None:
        raise NotImplementedError

    def _pack(self, payload: Any) -> bytes:
        data = pickle.dumps(payload)
        return self.PACKET_HEADER.pack(len(data)) + data

    def send(self, payload: Any) -> None:
        self._write(self._pack(payload))

    def receive(self) -> Any:
        header = self._read(self.PACKET_HEADER.size)
        payload_size = self.PACKET_HEADER.unpack(header)[0]
        payload_bytes = self._read(payload_size)
        return pickle.loads(payload_bytes)


class FileIOProtocol(Protocol):
    fd: Union[BinaryIO, IO[bytes]]

    def __init__(self, fd: Union[BinaryIO, IO[bytes]]):
        self.fd = fd

    def _read(self, size: int) -> bytes:
        return self.fd.read(size)

    def _write(self, data: bytes) -> None:
        self.fd.write(data)


class SocketIOProtocol(Protocol):
    sock: socket.socket

    def __init__(self, sock: socket.socket):
        self.sock = sock

    def _read(self, size: int) -> bytes:
        with io.BytesIO() as fp:
            while fp.tell() < size:
                chunk = self.sock.recv(size - fp.tell())
                if len(chunk) == 0:
                    raise ConnectionError("Remote didn't send any data")
                fp.write(chunk)
            return fp.getvalue()

    def _write(self, data: bytes) -> None:
        self.sock.send(data)


class AsyncProtocol:
    PACKET_HEADER = Protocol.PACKET_HEADER

    def __init__(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ):
        self.reader = reader
        self.writer = writer

    def _pack(self, payload: Any) -> bytes:
        data = pickle.dumps(payload)
        return self.PACKET_HEADER.pack(len(data)) + data

    async def send(self, payload: Any) -> None:
        self.writer.write(self._pack(payload))
        await self.writer.drain()

    async def receive(self) -> Any:
        header = await self.reader.readexactly(self.PACKET_HEADER.size)
        payload_size = self.PACKET_HEADER.unpack(header)[0]
        payload_bytes = await self.reader.readexactly(payload_size)
        return pickle.loads(payload_bytes)

    def close(self) -> None:
        if not self.writer.can_write_eof():
            self.writer.write_eof()
