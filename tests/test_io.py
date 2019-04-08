import struct

import pytest
from tempfile import NamedTemporaryFile
import aiomisc


pytestmark = pytest.mark.catch_loop_exceptions


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


async def test_object(loop):
    with NamedTemporaryFile(prefix='test_io') as tmp:
        afp1 = await aiomisc.io.async_open(tmp.name, 'w+', loop=loop)
        afp2 = await aiomisc.io.async_open(tmp.name, 'w+', loop=loop)

        async with afp1, afp2:
            assert afp1 == afp2
            assert hash(afp1) != hash(afp2)
            assert afp2 not in {afp1}
            assert afp1 in {afp1}

            for afp in (afp1, afp2):
                assert isinstance(afp.fileno(), int)
                assert isinstance(afp.mode, str)
                assert isinstance(afp.name, str)
                assert isinstance(afp.errors, str)
                assert isinstance(afp.line_buffering, bool)
                assert afp.newlines is None
