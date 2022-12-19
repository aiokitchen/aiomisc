import asyncio
from concurrent.futures import Executor
from functools import partial, total_ordering
from pathlib import Path
from typing import (
    IO, Any, Awaitable, BinaryIO, Callable, Generator, Generic, List, Optional,
    TextIO, TypeVar, Union,
)

from .compat import EventLoopMixin
from .thread_pool import threaded


T = TypeVar("T", bound=Union[str, bytes])


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
class AsyncFileIO(EventLoopMixin, Generic[T]):
    __slots__ = (
        "_fp", "executor", "__iterator_lock",
    ) + EventLoopMixin.__slots__

    _fp: Optional[Union[IO, BinaryIO, TextIO]]

    def __init__(
        self, fname: Union[str, Path], mode: str = "r",
        executor: Optional[Executor] = None, *args: Any,
        loop: Optional[asyncio.AbstractEventLoop] = None, **kwargs: Any,
    ):
        self.executor = executor
        self._loop = loop
        self._fp = None
        self.__open_args = (fname, mode, *args), kwargs
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
        self._fp = await self.__execute_in_thread(open, *args, **kwargs)

    @property
    def fp(self) -> Union[IO, BinaryIO, TextIO]:
        if self._fp is not None:
            return self._fp
        raise RuntimeError("file is not opened")

    def closed(self) -> bool:
        return self.fp.closed

    def __await__(self) -> Generator[Any, Any, "AsyncFileIO"]:
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
        del self._fp

    def __aiter__(self) -> "AsyncFileIOBase":
        return self

    async def __anext__(self) -> T:
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
        self, method: Callable[..., Any], *args: Any,
    ) -> Any:
        return await self.loop.run_in_executor(self.executor, method, *args)

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

    async def read(self, n: int = -1) -> T:
        return await self.__execute_in_thread(self.fp.read, n)

    async def readline(self, limit: int = -1) -> T:
        return await self.__execute_in_thread(self.fp.readline, limit)

    async def readlines(self, limit: int = -1) -> List[T]:
        return await self.__execute_in_thread(self.fp.readlines, limit)

    async def seek(self, offset: int, whence: int = 0) -> int:
        return await self.__execute_in_thread(self.fp.seek, offset, whence)

    async def truncate(self, size: Optional[int] = None) -> int:
        return await self.__execute_in_thread(self.fp.truncate, size)

    async def write(self, s: T) -> int:
        return await self.__execute_in_thread(self.fp.write, s)

    async def writelines(self, lines: List[T]) -> None:
        await self.__execute_in_thread(self.fp.writelines, lines)


AsyncFileIOBase = AsyncFileIO


class AsyncBinaryIO(AsyncFileIO[bytes]):
    @property
    def fp(self) -> BinaryIO:
        return self._fp  # type: ignore

    def __aiter__(self) -> "AsyncBytesFileIO":
        return self

    async def __aenter__(self) -> "AsyncBinaryIO":
        return await super().__aenter__()      # type: ignore


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

    def __aiter__(self) -> "AsyncTextFileIO":
        return self

    async def __aenter__(self) -> "AsyncTextIO":
        return await super().__aenter__()      # type: ignore


AsyncFileType = Union[
    AsyncBinaryIO,
    AsyncTextIO,
]

# Aliases
AsyncBytesFileIO = AsyncBinaryIO
AsyncTextFileIO = AsyncTextIO
AsyncFileT = AsyncFileType


def async_open(
    fname: Union[str, Path], mode: str = "r",
    *args: Any, **kwargs: Any,
) -> AsyncFileType:
    if "b" in mode:
        return AsyncBytesFileIO(
            fname, mode, *args, **kwargs,
        )
    return AsyncTextFileIO(fname, mode, *args, **kwargs)
