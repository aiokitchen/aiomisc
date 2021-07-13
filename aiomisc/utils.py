import asyncio
import itertools
import logging.handlers
import socket
from functools import wraps
from multiprocessing import cpu_count
from typing import (
    Any, Awaitable, Callable, Iterable, List, Optional, Tuple, TypeVar, Union,
)

from .thread_pool import ThreadPoolExecutor


T = TypeVar("T")
TimeoutType = Union[int, float]

try:
    import uvloop  # type: ignore
    event_loop_policy = uvloop.EventLoopPolicy()
except ImportError:
    event_loop_policy = asyncio.DefaultEventLoopPolicy()


log = logging.getLogger(__name__)


def chunk_list(iterable: Iterable[T], size: int) -> Iterable[List[T]]:
    """
    Split list or generator by chunks with fixed maximum size.
    """

    iterable = iter(iterable)

    item = list(itertools.islice(iterable, size))
    while item:
        yield item
        item = list(itertools.islice(iterable, size))


OptionsType = Iterable[Tuple[int, int, int]]


def bind_socket(
    *args: Any, address: str, port: int, options: OptionsType = (),
    reuse_addr: bool = True, reuse_port: bool = False,
    proto_name: Optional[str] = None
) -> socket.socket:
    """

    Bind socket and set ``setblocking(False)`` for just created socket.
    This detects ``address`` format and select socket family automatically.

    :param args: which will be passed to stdlib's socket constructor (optional)
    :param address: bind address
    :param port: bind port
    :param options: Tuple of pairs which contain socket option
                    to set and the option value.
    :param reuse_addr: set socket.SO_REUSEADDR
    :param reuse_port: set socket.SO_REUSEPORT
    :param proto_name: protocol name which will be logged after binding
    :return: socket.socket
    """

    if not args:
        if ":" in address:
            args = (socket.AF_INET6, socket.SOCK_STREAM)
        else:
            args = (socket.AF_INET, socket.SOCK_STREAM)

    sock = socket.socket(*args)
    sock.setblocking(False)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse_addr))
    if hasattr(socket, "SO_REUSEPORT"):
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEPORT, int(reuse_port),
        )
    else:
        log.warning("SO_REUSEPORT is not implemented by underlying library.")

    for level, option, value in options:
        sock.setsockopt(level, option, value)

    unix_address_family = getattr(socket, "AF_UNIX", None)
    if sock.family == unix_address_family:
        proto_name = proto_name or "unix"
        sock.bind(address)
    else:
        proto_name = proto_name or "tcp"
        sock.bind((address, port))

    sock_addr = sock.getsockname()
    if not isinstance(sock_addr, str):
        sock_addr = sock_addr[:2]

    if sock.family == socket.AF_INET6:
        log.info("Listening %s://[%s]:%s", proto_name, *sock_addr)
    elif sock.family == unix_address_family:
        log.info("Listening %s://%s", proto_name, sock_addr)
    else:
        log.info("Listening %s://%s:%s", proto_name, *sock_addr)

    return sock


def create_default_event_loop(
    pool_size: Optional[int] = None,
    policy: asyncio.AbstractEventLoopPolicy = event_loop_policy,
    debug: bool = False,
) -> Tuple[asyncio.AbstractEventLoop, ThreadPoolExecutor]:
    """
    Creates an event loop and thread pool executor

    :param pool_size: thread pool maximal size
    :param policy: event loop policy
    :param debug: set ``loop.set_debug(True)`` if True
    """
    try:
        asyncio.get_event_loop().close()
    except RuntimeError:
        pass  # event loop is not created yet

    asyncio.set_event_loop_policy(policy)

    loop = asyncio.new_event_loop()
    loop.set_debug(debug)
    asyncio.set_event_loop(loop)

    pool_size = pool_size or cpu_count()
    thread_pool = ThreadPoolExecutor(pool_size, statistic_name="default")
    loop.set_default_executor(thread_pool)

    return loop, thread_pool


def new_event_loop(
    pool_size: Optional[int] = None,
    policy: asyncio.AbstractEventLoopPolicy = event_loop_policy,
) -> asyncio.AbstractEventLoop:
    loop, thread_pool = create_default_event_loop(pool_size, policy)
    return loop


def shield(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    """
    Simple and useful decorator for wrap the coroutine to `asyncio.shield`.

    >>> @shield
    ... async def non_cancelable_func():
    ...     await asyncio.sleep(1)

    """

    async def awaiter(future: Awaitable[Any]) -> Any:
        return await future

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Awaitable[Any]:
        return wraps(func)(awaiter)(asyncio.shield(func(*args, **kwargs)))

    return wrap


class SelectResult:
    def __init__(self, length: int):
        self.length = length
        self.result_idx = None      # type: Optional[int]
        self.is_exception = None    # type: Optional[bool]
        self.value = None           # type: Any

    def set_result(self, idx: int, value: Any, is_exception: bool) -> None:
        if self.result_idx is not None:
            return

        self.value = value
        self.result_idx = idx
        self.is_exception = is_exception

    def result(self) -> T:
        if self.is_exception:
            raise self.value
        return self.value

    def done(self) -> bool:
        return self.result_idx is not None

    def __iter__(self) -> Iterable[Optional[T]]:
        for i in range(self.length):
            if i == self.result_idx:
                yield self.value
            else:
                yield None


def cancel_tasks(tasks: Iterable[asyncio.Future]) -> asyncio.Future:
    """
    All passed tasks will be cancelled and a new task will be returned.

    :param tasks: tasks which will be cancelled
    """

    future = asyncio.get_event_loop().create_future()
    future.set_result(None)

    if not tasks:
        return future

    cancelled_tasks = []
    exc = asyncio.CancelledError()

    for task in tasks:
        if task.done():
            continue

        if isinstance(task, asyncio.Task):
            task.cancel()
            cancelled_tasks.append(task)

        elif isinstance(task, asyncio.Future):
            task.set_exception(exc)

        else:
            log.warning(
                "Skipping object %r because it's not a Task or Future", task,
            )

    if not cancelled_tasks:
        return future

    waiter = asyncio.ensure_future(
        asyncio.gather(
            *cancelled_tasks, return_exceptions=True
        ),
    )

    return waiter


async def _select_waiter(
    idx: int, awaitable: Awaitable[T],
    result: SelectResult,
) -> None:
    try:
        ret = await awaitable
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return result.set_result(idx, e, is_exception=True)

    result.set_result(idx, ret, is_exception=False)


async def select(
    *awaitables: Awaitable[Any],
    return_exceptions: bool = False, cancel: bool = True,
    timeout: Optional[TimeoutType] = None,
    wait: bool = True, loop: Optional[asyncio.AbstractEventLoop] = None
) -> SelectResult:
    """

    :param awaitables: awaitable objects
    :param return_exceptions: if True exception will not be raised
                              just returned as result
    :param cancel: cancel unfinished coroutines (default True)
    :param timeout: execution timeout
    :param wait: when False and ``cancel=True``, unfinished coroutines will
                 be cancelled in the background.
    :param loop: event loop
    """

    loop = loop or asyncio.get_event_loop()
    result = SelectResult(len(awaitables))

    coroutines = [
        loop.create_task(_select_waiter(idx, coroutine, result))
        for idx, coroutine in enumerate(awaitables)
    ]

    _, pending = await loop.create_task(
        asyncio.wait(
            coroutines,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        ),
    )

    if cancel:
        cancelling = cancel_tasks(pending)

        if wait:
            await cancelling

    if result.is_exception and not return_exceptions:
        result.result()

    return result


def awaitable(
    func: Callable[..., Union[T, Awaitable[T]]],
) -> Callable[..., Awaitable[T]]:
    """

    Decorator wraps function and returns a function which returns
    awaitable object. In case than a function returns a future,
    the original future will be returned. In case then the function
    returns a coroutine, the original coroutine will be returned.
    In case than function returns non-awaitable object, it's will
    be wrapped to a new coroutine which just returns this object.
    It's useful when you don't want to check function result before
    use it in ``await`` expression.
    """

    # Avoid python 3.8+ warning
    if asyncio.iscoroutinefunction(func):
        return func     # type: ignore

    async def awaiter(obj: T) -> T:
        return obj

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Awaitable[T]:
        result = func(*args, **kwargs)

        if hasattr(result, "__await__"):
            return result       # type: ignore
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            return result       # type: ignore

        return awaiter(result)  # type: ignore

    return wrap
