import asyncio
import itertools
import logging.handlers
import socket
import uuid
from functools import wraps
from random import getrandbits
from typing import (
    Any, Awaitable, Callable, Collection, Coroutine, Generator, Iterable,
    Iterator, List, Optional, Set, Tuple, TypeVar, Union,
)

from .compat import (
    event_loop_policy, sock_set_nodelay, sock_set_reuseport, time_ns,
)
from .thread_pool import ThreadPoolExecutor


T = TypeVar("T", bound=Any)
TimeoutType = Union[int, float]


log = logging.getLogger(__name__)


def fast_uuid4() -> uuid.UUID:
    """ Fast UUID4 like identifier """
    return uuid.UUID(int=getrandbits(128), version=4)


__NODE = uuid.getnode()


def fast_uuid1() -> uuid.UUID:
    """ Fast UUID1 like identifier """
    value = time_ns()
    value = (value << 16) + getrandbits(16)
    value = (value << 48) + __NODE
    return uuid.UUID(int=value, version=1)


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
    *args: Any, address: str, port: int = 0, options: OptionsType = (),
    reuse_addr: bool = True, reuse_port: bool = True,
    proto_name: Optional[str] = None,
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

    if not args and ":" in address:
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)

    if reuse_addr:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    if reuse_port:
        sock_set_reuseport(sock, True)

    sock_set_nodelay(sock)

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

    current_loop_is_running = False
    try:
        current_loop = asyncio.get_event_loop()
        current_loop_is_running = current_loop.is_running()
        del current_loop
    except RuntimeError:
        pass

    if current_loop_is_running:
        raise RuntimeError(
            "Trying to create new event loop instance but another "
            "default loop in this thread is running right now.",
        )

    asyncio.set_event_loop_policy(policy)

    loop = asyncio.new_event_loop()
    loop.set_debug(debug)
    asyncio.set_event_loop(loop)

    pool_size = pool_size or ThreadPoolExecutor.DEFAULT_POOL_SIZE
    thread_pool = ThreadPoolExecutor(pool_size, statistic_name="default")
    loop.set_default_executor(thread_pool)

    return loop, thread_pool


def new_event_loop(
    pool_size: Optional[int] = None,
    policy: asyncio.AbstractEventLoopPolicy = event_loop_policy,
) -> asyncio.AbstractEventLoop:
    loop, thread_pool = create_default_event_loop(pool_size, policy)
    return loop


def shield(
    func: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """
    Simple and useful decorator for wrap the coroutine to `asyncio.shield`.

    >>> @shield
    ... async def non_cancelable_func():
    ...     await asyncio.sleep(1)

    """

    async def awaiter(future: Awaitable[Any]) -> Any:
        return await future

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Coroutine[Any, Any, T]:
        return wraps(func)(awaiter)(asyncio.shield(func(*args, **kwargs)))

    return wrap


class SelectResult(Collection):
    __slots__ = ("length", "result_idx", "is_exception", "value")

    def __init__(self, length: int):
        self.length = length
        self.result_idx = None      # type: Optional[int]
        self.is_exception = None    # type: Optional[bool]
        self.value = None           # type: Any

    def __len__(self) -> int:
        return self.length

    def __contains__(self, x: Any) -> bool:
        return self.value is x

    def set_result(self, idx: int, value: Any, is_exception: bool) -> None:
        if self.result_idx is not None:
            return

        self.value = value
        self.result_idx = idx
        self.is_exception = is_exception

    def result(self) -> Any:
        if self.is_exception:
            raise self.value
        return self.value

    def done(self) -> bool:
        return self.result_idx is not None

    def __iter__(self) -> Iterator[Optional[T]]:
        for i in range(self.length):
            yield self.value if i == self.result_idx else None


class SelectAwaitable:
    """
    Select one of passed awaitables
    """

    __slots__ = (
        "_awaitables", "_return_exceptions", "_timeout", "_wait",
        "__loop", "_cancel", "_result",
    )

    _result: SelectResult

    def __init__(
        self, *awaitables: Awaitable[T],
        return_exceptions: bool = False, cancel: bool = True,
        timeout: Optional[TimeoutType] = None,
        wait: bool = True, loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
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
        self.__loop = loop
        self._awaitables = awaitables
        self._cancel = cancel
        self._return_exceptions = return_exceptions
        self._timeout = timeout
        self._wait = wait

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self.__loop is None:
            self.__loop = asyncio.get_running_loop()
        return self.__loop

    async def __waiter(self, idx: int, awaitable: Awaitable[T]) -> None:
        try:
            ret = await awaitable
        except asyncio.CancelledError:
            raise
        except Exception as e:
            return self._result.set_result(idx, e, is_exception=True)
        self._result.set_result(idx, ret, is_exception=False)

    async def __run(
        self, coroutines: Iterable[asyncio.Future],
    ) -> SelectResult:
        try:
            _, pending = await asyncio.wait(
                coroutines,
                timeout=self._timeout,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if self._cancel:
                cancelling = cancel_tasks(pending)

                if self._wait:
                    await cancelling

            if self._result.is_exception and not self._return_exceptions:
                self._result.result()
            return self._result
        except TimeoutError as e:
            self._result.set_result(0, e, is_exception=True)
            raise
        except asyncio.CancelledError:
            await cancel_tasks(coroutines)
            raise

    def __await__(self) -> Generator[Any, None, SelectResult]:
        self._result = SelectResult(len(self._awaitables))
        coroutines = [
            asyncio.ensure_future(self.__waiter(idx, coroutine))
            for idx, coroutine in enumerate(self._awaitables)
        ]
        # Prevent double __await__ call
        del self._awaitables
        return self.__run(coroutines).__await__()


select = SelectAwaitable


def pending_futures(
    futures: Iterable[asyncio.Future],
) -> Iterator[asyncio.Future]:
    # Copying collection to ignore it
    # changes during iteration
    for future in tuple(futures):
        if future.done():
            continue
        yield future


def set_exception(
    futures: Iterable[asyncio.Future],
    exc: Union[BaseException] = asyncio.CancelledError(),
) -> Set[asyncio.Task]:
    cancelled_tasks = set()

    for future in pending_futures(futures):
        if isinstance(future, asyncio.Task):
            future.cancel()
            cancelled_tasks.add(future)
        elif isinstance(future, asyncio.Future):
            future.set_exception(exc)
        else:
            log.warning(
                "Skipping object %r because it's not a Task or Future",
                future,
            )
    return cancelled_tasks


def cancel_tasks(tasks: Iterable[asyncio.Future]) -> asyncio.Future:
    """
    All passed tasks will be cancelled and a new task will be returned.

    :param tasks: tasks which will be cancelled
    """

    future = asyncio.get_event_loop().create_future()
    future.set_result(None)

    if not tasks:
        return future

    exc = asyncio.CancelledError()
    cancelled_tasks = set_exception(tasks, exc)

    if not cancelled_tasks:
        return future

    waiter = asyncio.ensure_future(
        asyncio.gather(
            *cancelled_tasks, return_exceptions=True,
        ),
    )

    return waiter


AT = TypeVar("AT", bound=Any)


def awaitable(
    func: Callable[..., Union[AT, Awaitable[AT]]],
) -> Callable[..., Awaitable[AT]]:
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
        return func

    async def awaiter(obj: AT) -> AT:
        return obj

    @wraps(func)
    def wrap(*args: Any, **kwargs: Any) -> Awaitable[AT]:
        result = func(*args, **kwargs)

        if hasattr(result, "__await__"):
            return result
        if asyncio.iscoroutine(result) or asyncio.isfuture(result):
            return result

        return awaiter(result)      # type: ignore

    return wrap
