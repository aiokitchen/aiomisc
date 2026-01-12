import asyncio
import struct
import uuid
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import List

import pytest

import aiomisc
from aiomisc.io import AsyncFileIO
from tests import unix_only

pytestmark = pytest.mark.catch_loop_exceptions


compressors = pytest.mark.parametrize(
    "compression",
    list(aiomisc.io.Compression),
    ids=list(map(lambda c: c.name.lower(), aiomisc.io.Compression)),
)


async def test_simple(event_loop, tmp_path):
    tdir = Path(tmp_path)

    async with aiomisc.io.async_open(
        tdir / "test", "w+", loop=event_loop
    ) as afp:
        await afp.open()

        assert await afp.writable()
        assert await afp.readable()

        assert await afp.tell() == 0

        await afp.write("foo")
        assert await afp.tell() == 3

        await afp.seek(0)
        assert await afp.read() == "foo"

        await afp.write("\nbar\n")
        await afp.seek(0)

        assert await afp.readline() == "foo\n"
        assert await afp.readline() == "bar\n"

        await afp.flush()

        assert await afp.read() == ""

    with pytest.raises(ValueError):
        assert await afp.readable()

    with pytest.raises(ValueError):
        assert await afp.writable()


async def test_ordering(event_loop, tmp_path):
    tdir = Path(tmp_path)

    async with aiomisc.io.async_open(
        tdir / "file", "wb+", loop=event_loop
    ) as afp:
        await afp.seek(4)
        assert await afp.tell() == 4

        await afp.write(struct.pack("!I", 65535))
        assert await afp.tell() == 8

    assert afp.closed()

    async with aiomisc.io.async_open(
        tdir / "file", "rb+", loop=event_loop
    ) as afp:
        assert (await afp.read(4)) == b"\0\0\0\0"
        assert await afp.tell() == 4

        assert (await afp.read(4)) == struct.pack("!I", 65535)
        assert await afp.tell() == 8


async def test_async_for(event_loop, tmp_path):
    tdir = Path(tmp_path)
    afp: AsyncFileIO[str]

    async with aiomisc.io.async_open(
        tdir / "path", "w", loop=event_loop
    ) as afp:
        await afp.write("foo\nbar\nbaz\n")

    with open(tdir / "path") as fp:
        expected = []

        for line in fp:
            expected.append(line)

    assert expected

    result: list[str] = []
    async with aiomisc.io.async_open(
        tdir / "path", "r", loop=event_loop
    ) as afp:
        async for line in afp:
            result.append(line)

    assert result == expected


@unix_only
async def test_async_for_parallel(event_loop):
    tmp = NamedTemporaryFile(prefix="test_io")

    with tmp:
        async with aiomisc.io.async_open(
            tmp.name, "w+", loop=event_loop
        ) as afp:
            for _ in range(1024):
                await afp.write(f"{uuid.uuid4().hex}\n")

        with open(tmp.name) as fp:
            expected = set()

            for line in fp:
                expected.add(line)

        assert expected

        async with aiomisc.io.async_open(tmp.name, "r", loop=event_loop) as afp:
            result = set()

            async def reader():
                async for line in afp:
                    result.add(line)

            await asyncio.gather(reader(), reader(), reader(), reader())

    assert result == expected


@unix_only
async def test_object(event_loop):
    with NamedTemporaryFile(prefix="test_io") as tmp:
        afp1 = await aiomisc.io.async_open(tmp.name, "w+", loop=event_loop)
        afp2 = await aiomisc.io.async_open(tmp.name, "w+", loop=event_loop)

        async with afp1, afp2:
            assert afp1 == afp2
            assert hash(afp1) != hash(afp2)
            assert afp2 not in {afp1}
            assert afp1 in {afp1}

            with pytest.raises(TypeError):
                assert afp1 > afp2

            with pytest.raises(TypeError):
                assert afp1 < afp2

            for afp in (afp1, afp2):
                assert hash(afp) == hash(afp)
                assert isinstance(afp.fileno(), int)
                assert isinstance(afp.mode, str)
                assert isinstance(afp.name, str)
                assert isinstance(afp.errors, str)
                assert isinstance(afp.line_buffering, bool)
                assert afp.newlines is None


@compressors
async def test_compression(compression: aiomisc.io.Compression, tmp_path):
    fname = Path(tmp_path) / "test.file"

    async with aiomisc.io.async_open(
        fname, "w", compression=compression
    ) as afp:
        for i in range(1000):
            await afp.write(f"{i}\n")

    async with aiomisc.io.async_open(
        fname, "r", compression=compression
    ) as afp:
        for i in range(1000):
            assert await afp.readline() == f"{i}\n"
