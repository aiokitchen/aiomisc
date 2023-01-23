import asyncio
import bz2
import gzip
import lzma
import sys
from concurrent.futures import Executor
from enum import Enum
from functools import partial, total_ordering
from pathlib import Path
from typing import (
    IO, Any, AnyStr, Awaitable, Callable, Generator, Generic, List, Optional,
    TextIO, TypeVar, Union,
)

from .compat import EventLoopMixin


T = TypeVar("T", bound=Any)


def proxy_method_async(
    name: str,
    in_executor: bool = True,
) -> Callable[..., Any]:
    def wrap_to_future(
        loop: asyncio.AbstractEventLoop,
        func: Callable[..., T],
        *args: Any, **kwargs: Any,
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
        *args: Any, **kwargs: Any,
    ) -> Awaitable[T]:
        callee = partial(func, *args, **kwargs)
        # noinspection PyTypeChecker
        return loop.run_in_executor(executor, callee)

    async def method(self, *args, **kwargs):    # type: ignore
        func = getattr(self.fp, name)

        if in_executor:
            return await wrap_to_thread(
                self.loop, func, self.executor, *args, **kwargs,
            )

        return await wrap_to_future(self.loop, func, *args, **kwargs)

    method.__name__ = name
    return method


@total_ordering
class AsyncFileIO(EventLoopMixin, Generic[AnyStr]):
    __slots__ = (
        "_fp", "executor", "__iterator_lock",
    ) + EventLoopMixin.__slots__

    _fp: Optional[IO[AnyStr]]

    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return open

    def __init__(
        self, fname: Union[str, Path], mode: str = "r",
        executor: Optional[Executor] = None, *args: Any,
        loop: Optional[asyncio.AbstractEventLoop] = None, **kwargs: Any,
    ):
        self.executor = executor
        self._loop = loop
        self._fp = None
        self.__open_args = (str(fname), mode, *args), kwargs
        self.__iterator_lock = asyncio.Lock()

    @classmethod
    def open_fp(
        cls, fp: IO, executor: Optional[Executor] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> "AsyncFileIO":
        async_fp = cls(fp.name, mode=fp.mode, executor=executor, loop=loop)
        async_fp._fp = fp
        return async_fp

    async def open(self) -> None:
        if self._fp is not None:
            return

        args, kwargs = self.__open_args
        self._fp = await self.__execute_in_thread(
            self.get_opener(), *args, **kwargs,
        )

    @property
    def fp(self) -> IO[AnyStr]:
        if self._fp is not None:
            return self._fp
        raise RuntimeError("file is not opened")

    def closed(self) -> bool:
        return self.fp.closed

    def __await__(self) -> Generator[Any, Any, "AsyncFileIO"]:
        yield from self.open().__await__()
        return self

    async def __aenter__(self) -> "AsyncFileIO[AnyStr]":
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
        del self._fp

    def __aiter__(self) -> "AsyncFileIO[AnyStr]":
        return self

    async def __anext__(self) -> AnyStr:
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

    async def __execute_in_thread(
        self, method: Callable[..., Any], *args: Any, **kwargs: Any,
    ) -> Any:
        return await self.loop.run_in_executor(
            self.executor, partial(method, *args, **kwargs),
        )

    @property
    def mode(self) -> str:
        return self.fp.mode

    @property
    def name(self) -> str:
        return self.fp.name

    def fileno(self) -> int:
        return self.fp.fileno()

    def isatty(self) -> bool:
        return self.fp.isatty()

    async def close(self) -> None:
        return await self.__execute_in_thread(self.fp.close)

    def __getattr__(self, name: str) -> Callable[..., Awaitable[Any]]:
        async def method(*args: Any) -> Any:
            getter = getattr(self.fp, name)
            if callable(getter):
                return await self.__execute_in_thread(getter, *args)
            return getter
        method.__name__ = name
        return method

    async def tell(self) -> int:
        return self.fp.tell()

    async def readable(self) -> bool:
        return self.fp.readable()

    async def seekable(self) -> bool:
        return self.fp.seekable()

    async def writable(self) -> bool:
        return self.fp.writable()

    async def flush(self) -> None:
        await self.__execute_in_thread(self.fp.flush)

    async def read(self, n: int = -1) -> AnyStr:
        return await self.__execute_in_thread(self.fp.read, n)

    async def readline(self, limit: int = -1) -> AnyStr:
        return await self.__execute_in_thread(self.fp.readline, limit)

    async def readlines(self, limit: int = -1) -> List[AnyStr]:
        return await self.__execute_in_thread(self.fp.readlines, limit)

    async def seek(self, offset: int, whence: int = 0) -> int:
        return await self.__execute_in_thread(self.fp.seek, offset, whence)

    async def truncate(self, size: Optional[int] = None) -> int:
        return await self.__execute_in_thread(self.fp.truncate, size)

    async def write(self, s: AnyStr) -> int:
        return await self.__execute_in_thread(self.fp.write, s)

    async def writelines(self, lines: List[AnyStr]) -> None:
        await self.__execute_in_thread(self.fp.writelines, lines)


AsyncFileIOBase = AsyncFileIO


class AsyncBinaryIO(AsyncFileIO[bytes]):
    pass


class AsyncTextIO(AsyncFileIO[str]):
    @property
    def fp(self) -> TextIO:
        return self._fp     # type: ignore

    @property
    def newlines(self) -> Any:
        return self.fp.newlines

    @property
    def errors(self) -> Optional[str]:
        return self.fp.errors

    @property
    def line_buffering(self) -> int:
        return self.fp.line_buffering

    @property
    def encoding(self) -> str:
        return self.fp.encoding

    def buffer(self) -> AsyncBinaryIO:
        return AsyncBinaryIO.open_fp(self.fp.buffer)    # type: ignore


# Aliases
AsyncBytesFileIO = AsyncBinaryIO
AsyncTextFileIO = AsyncTextIO


class AsyncGzipBinaryIO(AsyncBytesFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return gzip.open  # type: ignore


class AsyncGzipTextIO(AsyncTextFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return gzip.open  # type: ignore


class AsyncBz2BinaryIO(AsyncBytesFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return bz2.open   # type: ignore


class AsyncBz2TextIO(AsyncTextFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return bz2.open   # type: ignore


class AsyncLzmaBinaryIO(AsyncBytesFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return lzma.open  # type: ignore


class AsyncLzmaTextIO(AsyncTextFileIO):
    @staticmethod
    def get_opener() -> Callable[..., IO[AnyStr]]:
        return lzma.open  # type: ignore


class Compression(Enum):
    NONE = (AsyncBinaryIO, AsyncTextIO)
    GZIP = (AsyncGzipBinaryIO, AsyncGzipTextIO)
    BZ2 = (AsyncBz2BinaryIO, AsyncBz2TextIO)
    LZMA = (AsyncLzmaBinaryIO, AsyncLzmaTextIO)


AsyncFileType = Union[AsyncFileIO[AnyStr], AsyncTextIO, AsyncBinaryIO]

# Deprecated excluded from __all__
AsyncFileT = AsyncFileType


def async_open(
    fname: Union[str, Path], mode: str = "r",
    compression: Compression = Compression.NONE,
    encoding: str = sys.getdefaultencoding(),
    *args: Any, **kwargs: Any,
) -> AsyncFileType:
    binary_io_class, text_io_class = compression.value

    if "b" in mode:
        return binary_io_class(fname, mode, *args, **kwargs)

    if "t" not in mode:
        mode = f"t{mode}"

    return text_io_class(fname, mode, encoding=encoding, *args, **kwargs)


__all__ = (
    "AsyncBinaryIO",
    "AsyncBz2BinaryIO",
    "AsyncBz2TextIO",
    "AsyncFileIO",
    "AsyncFileType",
    "AsyncGzipBinaryIO",
    "AsyncGzipTextIO",
    "AsyncLzmaBinaryIO",
    "AsyncLzmaTextIO",
    "AsyncTextIO",
    "Compression",
    "async_open",
)
