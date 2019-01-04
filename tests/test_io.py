import pytest
from tempfile import NamedTemporaryFile
from aiomisc.io import async_open


@pytest.mark.asyncio
async def test_simple(event_loop):
    tmp_file = NamedTemporaryFile(prefix='test_io')

    async with async_open(tmp_file.name, 'w+', loop=event_loop) as afp:
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
