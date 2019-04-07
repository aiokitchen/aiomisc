import struct

import pytest
from tempfile import NamedTemporaryFile
import aiomisc


async def test_simple(loop):
    tmp_file = NamedTemporaryFile(prefix='test_io')

    async with aiomisc.io.async_open(tmp_file.name, 'w+', loop=loop) as afp:
        await afp.open()

        assert await afp.writable()
        assert await afp.readable()

        assert await afp.tell() == 0

        await afp.write('foo')
        assert await afp.tell() == 3

        await afp.seek(0)
        assert await afp.read() == 'foo'

        await afp.write('\nbar\n')
        await afp.seek(0)

        assert await afp.readline() == 'foo\n'
        assert await afp.readline() == 'bar\n'

        await afp.flush()

        assert await afp.read() == ''

    with pytest.raises(ValueError):
        assert await afp.readable()

    with pytest.raises(ValueError):
        assert await afp.writable()


async def test_ordering(loop):
    tmp = NamedTemporaryFile(prefix='test_io')

    with tmp:
        async with aiomisc.io.async_open(tmp.name, 'wb+', loop=loop) as afp:
            await afp.seek(4)
            assert await afp.tell() == 4

            await afp.write(struct.pack("!I", 65535))
            assert await afp.tell() == 8

        assert afp.closed()

        async with aiomisc.io.async_open(tmp.name, 'rb+', loop=loop) as afp:
            assert (await afp.read(4)) == b'\0\0\0\0'
            assert await afp.tell() == 4

            assert (await afp.read(4)) == struct.pack("!I", 65535)
            assert await afp.tell() == 8


async def test_async_for(loop):
    tmp = NamedTemporaryFile(prefix='test_io')

    with tmp:
        async with aiomisc.io.async_open(tmp.name, 'w+', loop=loop) as afp:
            await afp.write("foo\nbar\nbaz\n")

        with open(tmp.name, 'w+') as fp:
            expected = []

            for line in fp:
                expected.append(line)

        async with aiomisc.io.async_open(tmp.name, 'rb+', loop=loop) as afp:
            result = []
            async for line in afp:
                result.append(line)

    assert result == expected
