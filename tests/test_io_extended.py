import asyncio
import gzip
import bz2
import lzma
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

import aiomisc
from aiomisc.io import (
    AsyncBinaryIO,
    AsyncBz2BinaryIO,
    AsyncBz2TextIO,
    AsyncFileIO,
    AsyncGzipBinaryIO,
    AsyncGzipTextIO,
    AsyncLzmaBinaryIO,
    AsyncLzmaTextIO,
    AsyncTextIO,
    Compression,
    async_open,
)
from tests import unix_only


pytestmark = pytest.mark.catch_loop_exceptions


class TestAsyncFileIOGetOpener:
    def test_get_opener_default(self):
        opener = AsyncFileIO.get_opener()
        assert opener is open

    def test_get_opener_gzip_binary(self):
        opener = AsyncGzipBinaryIO.get_opener()
        assert opener is gzip.open

    def test_get_opener_gzip_text(self):
        opener = AsyncGzipTextIO.get_opener()
        assert opener is gzip.open

    def test_get_opener_bz2_binary(self):
        opener = AsyncBz2BinaryIO.get_opener()
        assert opener is bz2.open

    def test_get_opener_bz2_text(self):
        opener = AsyncBz2TextIO.get_opener()
        assert opener is bz2.open

    def test_get_opener_lzma_binary(self):
        opener = AsyncLzmaBinaryIO.get_opener()
        assert opener is lzma.open

    def test_get_opener_lzma_text(self):
        opener = AsyncLzmaTextIO.get_opener()
        assert opener is lzma.open


class TestAsyncFileIOWriteMethods:
    async def test_writelines(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"

        async with aiomisc.io.async_open(
            test_file, "w", loop=event_loop
        ) as afp:
            await afp.writelines(["line1\n", "line2\n", "line3\n"])

        content = test_file.read_text()
        assert content == "line1\nline2\nline3\n"

    async def test_truncate(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        async with aiomisc.io.async_open(
            test_file, "r+", loop=event_loop
        ) as afp:
            result = await afp.truncate(5)
            assert result == 5

        content = test_file.read_text()
        assert content == "hello"


class TestAsyncFileIOSeekable:
    async def test_seekable(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            assert await afp.seekable() is True


class TestAsyncFileIOReadlines:
    async def test_readlines(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("line1\nline2\nline3\n")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            lines = await afp.readlines()
            assert lines == ["line1\n", "line2\n", "line3\n"]


class TestAsyncTextIOProperties:
    async def test_buffer(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            buffer = afp.buffer()
            assert isinstance(buffer, AsyncBinaryIO)

    async def test_encoding(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            assert isinstance(afp.encoding, str)


class TestAsyncBinaryIO:
    async def test_binary_read_write(self, tmp_path, event_loop):
        test_file = tmp_path / "test.bin"

        async with aiomisc.io.async_open(
            test_file, "wb", loop=event_loop
        ) as afp:
            await afp.write(b"\x00\x01\x02\x03")

        async with aiomisc.io.async_open(
            test_file, "rb", loop=event_loop
        ) as afp:
            content = await afp.read()
            assert content == b"\x00\x01\x02\x03"


class TestCompression:
    def test_compression_enum_values(self):
        assert Compression.NONE.value == (AsyncBinaryIO, AsyncTextIO)
        assert Compression.GZIP.value == (AsyncGzipBinaryIO, AsyncGzipTextIO)
        assert Compression.BZ2.value == (AsyncBz2BinaryIO, AsyncBz2TextIO)
        assert Compression.LZMA.value == (AsyncLzmaBinaryIO, AsyncLzmaTextIO)


class TestAsyncOpen:
    async def test_async_open_binary(self, tmp_path, event_loop):
        test_file = tmp_path / "test.bin"

        afp = async_open(test_file, "wb", loop=event_loop)
        assert isinstance(afp, AsyncBinaryIO)

        async with afp:
            await afp.write(b"binary data")

    async def test_async_open_text(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"

        afp = async_open(test_file, "w", loop=event_loop)
        assert isinstance(afp, AsyncTextIO)

        async with afp:
            await afp.write("text data")

    async def test_async_open_with_encoding(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"

        afp = async_open(test_file, "w", encoding="utf-8", loop=event_loop)
        assert isinstance(afp, AsyncTextIO)

        async with afp:
            await afp.write("encoded text")


class TestCompressedFiles:
    async def test_gzip_binary(self, tmp_path, event_loop):
        test_file = tmp_path / "test.gz"

        async with async_open(
            test_file, "wb", compression=Compression.GZIP, loop=event_loop
        ) as afp:
            await afp.write(b"compressed binary data")

        async with async_open(
            test_file, "rb", compression=Compression.GZIP, loop=event_loop
        ) as afp:
            content = await afp.read()
            assert content == b"compressed binary data"

    async def test_bz2_binary(self, tmp_path, event_loop):
        test_file = tmp_path / "test.bz2"

        async with async_open(
            test_file, "wb", compression=Compression.BZ2, loop=event_loop
        ) as afp:
            await afp.write(b"bz2 compressed data")

        async with async_open(
            test_file, "rb", compression=Compression.BZ2, loop=event_loop
        ) as afp:
            content = await afp.read()
            assert content == b"bz2 compressed data"

    async def test_lzma_binary(self, tmp_path, event_loop):
        test_file = tmp_path / "test.xz"

        async with async_open(
            test_file, "wb", compression=Compression.LZMA, loop=event_loop
        ) as afp:
            await afp.write(b"lzma compressed data")

        async with async_open(
            test_file, "rb", compression=Compression.LZMA, loop=event_loop
        ) as afp:
            content = await afp.read()
            assert content == b"lzma compressed data"


class TestAsyncFileIOProperties:
    async def test_isatty(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            assert afp.isatty() is False

    async def test_fileno(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            fd = afp.fileno()
            assert isinstance(fd, int)
            assert fd > 0

    async def test_mode(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            assert "r" in afp.mode

    async def test_name(self, tmp_path, event_loop):
        test_file = tmp_path / "test.txt"
        test_file.write_text("test")

        async with aiomisc.io.async_open(
            test_file, "r", loop=event_loop
        ) as afp:
            assert afp.name == str(test_file)
