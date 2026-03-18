import asyncio
import io
import os
import pickle
import signal
import socket
from struct import Struct
from threading import Event
from unittest.mock import MagicMock, patch

import pytest

from aiomisc import threaded
from aiomisc_worker import (
    COOKIE_SIZE,
    HASHER,
    INET_AF,
    INT_SIGNAL,
    PacketTypes,
    SALT_SIZE,
    SIGNAL,
)
from aiomisc_worker.protocol import (
    ADDRESS_FAMILY,
    AsyncProtocol,
    FileIOProtocol,
    Protocol,
    SocketIOProtocol,
)

from tests import unix_only


class TestPacketTypes:
    def test_packet_types_values(self):
        assert PacketTypes.REQUEST == 0
        assert PacketTypes.EXCEPTION == 1
        assert PacketTypes.RESULT == 2
        assert PacketTypes.CANCELLED == 3
        assert PacketTypes.AUTH == 50
        assert PacketTypes.AUTH_FAIL == 58
        assert PacketTypes.AUTH_OK == 59
        assert PacketTypes.BAD_INITIALIZER == 60
        assert PacketTypes.BAD_PACKET == 254


class TestConstants:
    def test_salt_size(self):
        assert SALT_SIZE == 64

    def test_cookie_size(self):
        assert COOKIE_SIZE == 128

    def test_hasher(self):
        import hashlib
        assert HASHER is hashlib.sha256

    def test_inet_af(self):
        assert INET_AF == socket.AF_INET6


class TestProtocol:
    def test_packet_header(self):
        header = Protocol.PACKET_HEADER
        assert isinstance(header, Struct)
        assert header.size == 4  # !L = unsigned long, 4 bytes


class TestFileIOProtocol:
    def test_init(self, tmp_path):
        test_file = tmp_path / "test.bin"
        with open(test_file, "wb") as fp:
            proto = FileIOProtocol(fp)
            assert proto.fd is fp

    def test_write(self, tmp_path):
        test_file = tmp_path / "test.bin"
        with open(test_file, "wb") as fp:
            proto = FileIOProtocol(fp)
            proto._write(b"hello")

        assert test_file.read_bytes() == b"hello"

    def test_read(self, tmp_path):
        test_file = tmp_path / "test.bin"
        test_file.write_bytes(b"hello world")

        with open(test_file, "rb") as fp:
            proto = FileIOProtocol(fp)
            data = proto._read(5)
            assert data == b"hello"

    def test_send_receive_primitives(self, tmp_path):
        test_file = tmp_path / "test.bin"

        # Test various data types
        test_data = [
            42,
            3.14,
            "hello",
            b"bytes",
            [1, 2, 3],
            {"key": "value"},
            (1, 2, 3),
            None,
            True,
            False,
        ]

        for data in test_data:
            with open(test_file, "wb") as fp:
                proto = FileIOProtocol(fp)
                proto.send(data)

            with open(test_file, "rb") as fp:
                proto = FileIOProtocol(fp)
                result = proto.receive()
                assert result == data

    def test_send_receive_complex(self, tmp_path):
        test_file = tmp_path / "test.bin"

        data = {
            "nested": {
                "list": [1, 2, {"deep": "value"}],
                "tuple": (1, 2, 3),
            },
            "bytes": b"\x00\x01\x02",
        }

        with open(test_file, "wb") as fp:
            proto = FileIOProtocol(fp)
            proto.send(data)

        with open(test_file, "rb") as fp:
            proto = FileIOProtocol(fp)
            result = proto.receive()
            assert result == data

    def test_pack(self, tmp_path):
        test_file = tmp_path / "test.bin"
        with open(test_file, "wb") as fp:
            proto = FileIOProtocol(fp)
            packed = proto._pack({"test": "data"})

            # First 4 bytes should be the length
            length = Struct("!L").unpack(packed[:4])[0]
            assert length == len(packed) - 4

            # Rest should be pickled data
            unpacked = pickle.loads(packed[4:])
            assert unpacked == {"test": "data"}


class TestSocketIOProtocol:
    def test_init(self):
        sock = MagicMock(spec=socket.socket)
        proto = SocketIOProtocol(sock)
        assert proto.sock is sock

    def test_write(self):
        sock = MagicMock(spec=socket.socket)
        proto = SocketIOProtocol(sock)
        proto._write(b"hello")
        sock.send.assert_called_once_with(b"hello")

    def test_read_connection_error(self):
        sock = MagicMock(spec=socket.socket)
        sock.recv.return_value = b""  # Empty response indicates closed

        proto = SocketIOProtocol(sock)
        with pytest.raises(ConnectionError):
            proto._read(10)

    def test_read_partial_chunks(self):
        sock = MagicMock(spec=socket.socket)
        # Simulate receiving data in chunks
        sock.recv.side_effect = [b"hel", b"lo", b" wor", b"ld"]

        proto = SocketIOProtocol(sock)
        result = proto._read(11)
        assert result == b"hello world"


class TestAsyncProtocol:
    async def test_init(self):
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)

        proto = AsyncProtocol(reader, writer)
        assert proto.reader is reader
        assert proto.writer is writer

    async def test_pack(self):
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)

        proto = AsyncProtocol(reader, writer)
        packed = proto._pack({"test": "data"})

        length = Struct("!L").unpack(packed[:4])[0]
        assert length == len(packed) - 4

    async def test_send(self):
        from unittest.mock import AsyncMock

        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.drain = AsyncMock()

        proto = AsyncProtocol(reader, writer)
        await proto.send({"test": "data"})

        writer.write.assert_called_once()

    async def test_receive(self):
        from unittest.mock import AsyncMock

        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)

        # Prepare the data
        data = pickle.dumps({"test": "data"})
        header = Struct("!L").pack(len(data))

        async def mock_readexactly(n):
            return header if n == 4 else data

        reader.readexactly = mock_readexactly

        proto = AsyncProtocol(reader, writer)
        result = await proto.receive()
        assert result == {"test": "data"}

    async def test_close_cannot_write_eof(self):
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.can_write_eof.return_value = False

        proto = AsyncProtocol(reader, writer)
        proto.close()

        writer.write_eof.assert_called_once()

    async def test_close_can_write_eof(self):
        reader = MagicMock(spec=asyncio.StreamReader)
        writer = MagicMock(spec=asyncio.StreamWriter)
        writer.can_write_eof.return_value = True

        proto = AsyncProtocol(reader, writer)
        proto.close()

        writer.write_eof.assert_not_called()


class TestAddressFamily:
    def test_address_family_unix(self):
        import platform
        if platform.system() == "Windows":
            assert ADDRESS_FAMILY == socket.AF_INET6
        else:
            assert ADDRESS_FAMILY == socket.AF_UNIX
