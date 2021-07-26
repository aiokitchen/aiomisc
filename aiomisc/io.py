import asyncio
from concurrent.futures import Executor
from functools import partial, total_ordering
from pathlib import Path
from typing import Any, Awaitable, Callable, Generator, TypeVar, Union

from .thread_pool import threaded


T = TypeVar("T")


def proxy_method_async(
    name: str,
    in_executor: bool = True,
) -> Callable[..., Any]:
    def wrap_to_future(
        loop: asyncio.AbstractEventLoop,
        func: Callable[..., T],
        *args: Any, **kwargs: Any
    ) -> asyncio.Future:
        future = loop.create_future()

        def _inner():   # type: ignore
            try:
                return future.set_result(func(*args, **kwargs))
            except Exception as e:
                return future.set_exception(e)

        loop.call_soon(_inner)
        return future

    def wrap_to_thread(
        loop: asyncio.AbstractEventLoop, func: Callable[..., T],
        executor: Executor,
        *args: Any, **kwargs: Any
    ) -> Awaitable[T]:
        callee = partial(func, *args, **kwargs)
        # noinspection PyTypeChecker
        return loop.run_in_executor(executor, callee)

    async def method(self, *args, **kwargs):    # type: ignore
        func = getattr(self.fp, name)

        if in_executor:
            return await wrap_to_thread(
                self.loop, func, self.executor, *args, **kwargs
            )

        return await wrap_to_future(self.loop, func, *args, **kwargs)

    method.__name__ = name
    return method


def proxy_method(name: str) -> Callable[..., Awaitable[Any]]:
    def method(self: Any, *args: Any, **kwargs: Any) -> Any:
        return getattr(self.fp, name)(*args, **kwargs)

    method.__name__ = name
    return method


def proxy_property(name: str) -> property:
    def fset(self: Any, value: Any) -> None:
        setattr(self.fp, name, value)

    def fget(self: Any) -> Any:
        return getattr(self.fp, name)

    def fdel(self: Any) -> None:
        delattr(self.fp, name)

    return property(fget, fset, fdel)


@total_ordering
class AsyncFileIOBase:
    __slots__ = ("loop", "__opener", "fp", "executor", "__iterator_lock")

    opener = staticmethod(threaded(open))

    def __init__(
        self, fname: Union[str, Path], mode: str = "r",
        executor: Executor = None, *args: Any, **kwargs: Any
    ):
        self.loop = kwargs.pop("loop", asyncio.get_event_loop())
        self.fp = None
        self.executor = executor
        self.__opener = partial(self.opener, fname, mode, *args, **kwargs)
        self.__iterator_lock = asyncio.Lock()

    def closed(self) -> bool:
        if self.fp is None:
            raise RuntimeError("file is not opened")
        return self.fp.closed

    async def open(self) -> None:
        if self.fp is not None:
            return

        self.fp = await self.__opener()

    def __await__(self) -> Generator[Any, Any, "AsyncFileIOBase"]:
        yield from self.open().__await__()
        return self

    async def __aenter__(self) -> "AsyncFileIOBase":
        await self.open()
        return self

    async def __aexit__(
        self, exc_type: Any,
        exc_val: Any, exc_tb: Any,
    ) -> None:
        if self.fp is None:
            raise RuntimeError("file is not opened")

        await self.loop.run_in_executor(
            None, self.fp.__exit__, exc_type, exc_val, exc_tb,
        )

    def __del__(self) -> None:
        if not self.fp or self.fp.closed:
            return

        self.fp.close()
        del self.fp

    def __aiter__(self) -> "AsyncFileIOBase":
        return self

    async def __anext__(self) -> Union[str, bytes]:
        async with self.__iterator_lock:
            line = await self.readline()

        if not len(line):
            raise StopAsyncIteration

        return line

    def __eq__(self, other: Any) -> bool:
        return (
            self.__class__, self.fp.__eq__(other),
        ) == (
            other.__class__, self.fp.__eq__(other),
        )

    def __lt__(self, other: Any) -> bool:
        return self.fp < other.fp

    def __hash__(self) -> int:
        return hash((self.__class__, self.fp))

    fileno = proxy_method("fileno")
    isatty = proxy_method("isatty")

    mode = proxy_property("mode")
    name = proxy_property("name")

    close = proxy_method_async("close")
    detach = proxy_method_async("detach")
    flush = proxy_method_async("flush")
    peek = proxy_method_async("peek")
    raw = proxy_property("raw")
    read = proxy_method_async("read")
    read1 = proxy_method_async("read1")
    readinto = proxy_method_async("readinto")
    readinto1 = proxy_method_async("readinto1")
    readline = proxy_method_async("readline")
    readlines = proxy_method_async("readlines")
    seek = proxy_method_async("seek")
    peek = proxy_method_async("peek")
    truncate = proxy_method_async("truncate")
    write = proxy_method_async("write")
    writelines = proxy_method_async("writelines")

    tell = proxy_method_async("tell", in_executor=False)
    readable = proxy_method_async("readable", in_executor=False)
    seekable = proxy_method_async("seekable", in_executor=False)
    writable = proxy_method_async("writable", in_executor=False)


class AsyncTextFileIOBase:
    newlines = proxy_property("newlines")
    errors = proxy_property("errors")
    line_buffering = proxy_property("line_buffering")
    encoding = proxy_property("encoding")
    buffer = proxy_property("buffer")


class AsyncBytesFileIOBase:
    pass


class AsyncTextFileIO(AsyncFileIOBase, AsyncTextFileIOBase):
    pass


class AsyncBytesFileIO(AsyncFileIOBase, AsyncBytesFileIOBase):
    pass


AsyncFileT = Union[
    AsyncBytesFileIO,
    AsyncTextFileIO,
]


def async_open(
    fname: Union[str, Path], mode: str = "r",
    *args: Any, **kwargs: Any
) -> AsyncFileT:
    if "b" in mode:
        return AsyncBytesFileIO(
            fname, mode, *args, **kwargs
        )
    return AsyncTextFileIO(fname, mode, *args, **kwargs)
