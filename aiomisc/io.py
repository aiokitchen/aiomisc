import asyncio
from functools import partial, total_ordering
from typing import Union

from .thread_pool import threaded


def proxy_method_async(name, in_executor=True):
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


def proxy_method(name):
    def method(self, *args, **kwargs):
        return getattr(self.fp, name)(*args, **kwargs)

    method.__name__ = name
    return method


def proxy_property(name):
    def fset(self, value):
        setattr(self.fp, name, value)

    def fget(self):
        return getattr(self.fp, name)

    def fdel(self):
        delattr(self.fp, name)

    return property(fget, fset, fdel)


@total_ordering
class AsyncFileIOBase:
    __slots__ = ('loop', '__opener', 'fp', 'executor', '__iterator_lock')

    opener = staticmethod(threaded(open))

    def __init__(self, fname, mode="r", executor=None, *args, **kwargs):
        self.loop = kwargs.pop('loop', asyncio.get_event_loop())
        self.fp = None
        self.executor = executor
        self.__opener = partial(self.opener, fname, mode, *args, **kwargs)
        self.__iterator_lock = asyncio.Lock(loop=self.loop)

    def closed(self):
        return self.fp.closed

    async def open(self):
        if self.fp is not None:
            return

        self.fp = await self.__opener()

    def __await__(self):
        yield from self.open().__await__()
        return self

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
        async with self.__iterator_lock:
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
        return hash((self.__class__, self.fp))

    fileno = proxy_method('fileno')
    isatty = proxy_method('isatty')

    mode = proxy_property('mode')
    name = proxy_property('name')

    close = proxy_method_async('close')
    detach = proxy_method_async('detach')
    flush = proxy_method_async('flush')
    peek = proxy_method_async('peek')
    raw = proxy_method_async('raw')
    read = proxy_method_async('read')
    read1 = proxy_method_async('read1')
    readinto = proxy_method_async('readinto')
    readinto1 = proxy_method_async('readinto1')
    readline = proxy_method_async('readline')
    readlines = proxy_method_async('readlines')
    seek = proxy_method_async('seek')
    peek = proxy_method_async('peek')
    truncate = proxy_method_async('truncate')
    write = proxy_method_async('write')
    writelines = proxy_method_async('writelines')

    tell = proxy_method_async('tell', in_executor=False)
    readable = proxy_method_async('readable', in_executor=False)
    seekable = proxy_method_async('seekable', in_executor=False)
    writable = proxy_method_async('writable', in_executor=False)


class AsyncTextFileIOBase:
    newlines = proxy_property('newlines')
    errors = proxy_property('errors')
    line_buffering = proxy_property('line_buffering')
    encoding = proxy_property('encoding')
    buffer = proxy_property('buffer')


class AsyncBytesFileIOBase:
    raw = proxy_property('raw')


class AsyncTextFileIO(AsyncFileIOBase, AsyncTextFileIOBase):
    pass


class AsyncBytesFileIO(AsyncFileIOBase, AsyncBytesFileIOBase):
    pass


AsyncFileT = Union[
    AsyncBytesFileIO,
    AsyncTextFileIO,
]


def async_open(fname, mode="r", *args, **kwargs) -> AsyncFileT:
    if 'b' in mode:
        return AsyncBytesFileIO(fname, mode=mode, *args, **kwargs)
    return AsyncTextFileIO(fname, mode=mode, *args, **kwargs)
