import asyncio
from functools import partial

from .thread_pool import threaded


opener = threaded(open)


def async_method(name):
    async def method(self, *args, **kwargs):
        func = getattr(self.fp, name)

        return await self.loop.run_in_executor(
            None, partial(func, *args, **kwargs)
        )

    method.__name__ = name
    return method


# noinspection PyPep8Naming
class async_open:
    __slots__ = ('loop', 'name', 'mode', 'opener', 'fp', 'isatty', 'fileno')

    def __init__(self, fname, mode="r", *args, **kwargs):
        self.loop = kwargs.pop('loop', asyncio.get_event_loop())
        self.name = fname
        self.mode = mode
        self.opener = partial(opener, self.name, self.mode, *args, **kwargs)
        self.fp = None
        self.isatty = None
        self.fileno = None

    def closed(self):
        return self.fp.closed

    async def open(self):
        if self.fp is not None:
            return

        self.fp = await self.opener()
        self.fileno = self.fp.fileno()
        self.isatty = self.fp.isatty

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.loop.run_in_executor(
            None, self.fp.__exit__, exc_type, exc_val, exc_tb
        )

    close = async_method('close')
    detach = async_method('detach')
    flush = async_method('flush')
    peek = async_method('peek')
    raw = async_method('raw')
    read = async_method('read')
    read1 = async_method('read1')
    readable = async_method('readable')
    readinto = async_method('readinto')
    readinto1 = async_method('readinto1')
    readline = async_method('readline')
    readlines = async_method('readlines')
    seek = async_method('seek')
    seekable = async_method('seekable')
    tell = async_method('tell')
    truncate = async_method('truncate')
    write = async_method('write')
    writable = async_method('writable')
    writelines = async_method('writelines')
