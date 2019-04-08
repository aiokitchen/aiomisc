import asyncio
from functools import partial, total_ordering

from .thread_pool import threaded


opener = threaded(open)


def async_method(name, in_executor=True):
    def wrap_to_future(loop, func, *args, **kwargs):
        future = loop.create_future()

        def _inner():
            try:
                return future.set_result(func(*args, **kwargs))
            except Exception as e:
                return future.set_exception(e)

        loop.call_soon(_inner)
        return future

    def wrap_to_thread(loop, func, executor, *args, **kwargs):
        callee = partial(func, *args, **kwargs)
        return loop.run_in_executor(executor, callee)

    async def method(self, *args, **kwargs):
        func = getattr(self.fp, name)

        if in_executor:
            return await wrap_to_thread(
                self.loop, func, self.executor, *args, **kwargs
            )

        return await wrap_to_future(self.loop, func, *args, **kwargs)

    method.__name__ = name
    return method


def bypass_method(name):
    def method(self, *args, **kwargs):
        return getattr(self.fp, name)(*args, **kwargs)

    method.__name__ = name
    return method


def bypass_property(name):
    def fset(self, value):
        setattr(self.fp, name, value)

    def fget(self):
        return getattr(self.fp, name)

    def fdel(self):
        delattr(self.fp, name)

    return property(fget, fset, fdel)


# noinspection PyPep8Naming
@total_ordering
class AsyncFileIOBase:
    __slots__ = ('loop', 'opener', 'fp', 'executor')

    def __init__(self, fname, mode="r", executor=None, *args, **kwargs):
        self.loop = kwargs.pop('loop', asyncio.get_event_loop())
        self.opener = partial(opener, fname, mode, *args, **kwargs)
        self.fp = None
        self.executor = executor

    def closed(self):
        return self.fp.closed

    async def open(self):
        if self.fp is not None:
            return

        self.fp = await self.opener()

    async def __aenter__(self):
        await self.open()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await self.loop.run_in_executor(
            None, self.fp.__exit__, exc_type, exc_val, exc_tb
        )

    def __del__(self):
        if not self.fp or self.fp.closed:
            return

        self.fp.close()
        del self.fp

    def __aiter__(self):
        return self

    async def __anext__(self):
        line = await self.readline()
        if not len(line):
            raise StopAsyncIteration

        return line

    def __eq__(self, other: "async_open"):
        return (
            self.__class__, self.fp.__eq__(other)
        ) == (
            other.__class__, self.fp.__eq__(other)
        )

    def __lt__(self, other: "async_open"):
        return self.fp < other.fp

    def __hash__(self):
        return hash((self.__class__, self.fp.__hash__()))

    fileno = bypass_method('fileno')

    isatty = bypass_method('isatty')
    mode = bypass_property('mode')
    name = bypass_property('name')

    close = async_method('close')
    detach = async_method('detach')
    flush = async_method('flush')
    peek = async_method('peek')
    raw = async_method('raw')
    read = async_method('read')
    read1 = async_method('read1')
    readinto = async_method('readinto')
    readinto1 = async_method('readinto1')
    readline = async_method('readline')
    readlines = async_method('readlines')
    seek = async_method('seek')
    peek = async_method('peek')
    truncate = async_method('truncate')
    write = async_method('write')
    writelines = async_method('writelines')

    tell = async_method('tell', in_executor=False)
    readable = async_method('readable', in_executor=False)
    seekable = async_method('seekable', in_executor=False)
    writable = async_method('writable', in_executor=False)


class AsyncTextFileIO(AsyncFileIOBase):
    newlines = bypass_property('newlines')
    errors = bypass_property('errors')
    line_buffering = bypass_property('line_buffering')
    encoding = bypass_property('encoding')
    buffer = bypass_property('buffer')


class AsyncBytesFileIO(AsyncFileIOBase):
    raw = bypass_property('raw')


def async_open(fname, mode="r", *args, **kwargs) -> AsyncFileIOBase:
    if 'b' in mode:
        return AsyncBytesFileIO(fname, mode=mode, *args, **kwargs)

    return AsyncTextFileIO(fname, mode=mode, *args, **kwargs)
