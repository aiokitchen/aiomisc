import asyncio
import itertools
import logging.handlers
import socket
from functools import wraps, partial
from multiprocessing import cpu_count
from types import CoroutineType
from typing import Any, Iterable, Tuple

try:
    from typing import Coroutine
except ImportError:
    Coroutine = CoroutineType


try:
    import uvloop
    event_loop_policy = uvloop.EventLoopPolicy()
except ImportError:
    event_loop_policy = asyncio.DefaultEventLoopPolicy()


from .thread_pool import ThreadPoolExecutor


log = logging.getLogger(__name__)


def chunk_list(iterable: Iterable[Any], size: int):
    """
    Split list or generator by chunks with fixed maximum size.
    """

    iterable = iter(iterable)

    item = list(itertools.islice(iterable, size))
    while item:
        yield item
        item = list(itertools.islice(iterable, size))


OptionsType = Iterable[Tuple[int, int, int]]


def bind_socket(*args, address: str, port: int, options: OptionsType = (),
                reuse_addr: bool = True, reuse_port: bool = False,
                proto_name: str = 'tcp'):
    """

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
        if ':' in address:
            args = (socket.AF_INET6, socket.SOCK_STREAM)
        else:
            args = (socket.AF_INET, socket.SOCK_STREAM)

    sock = socket.socket(*args)
    sock.setblocking(False)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse_addr))
    if hasattr(socket, 'SO_REUSEPORT'):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, int(reuse_port))
    else:
        log.warning('SO_REUSEPORT is not implemented by underlying library.')

    for level, option, value in options:
        sock.setsockopt(level, option, value)

    sock.bind((address, port))
    sock_addr = sock.getsockname()[:2]

    if sock.family == socket.AF_INET6:
        log.info('Listening %s://[%s]:%s', proto_name, *sock_addr)
    else:
        log.info('Listening %s://%s:%s', proto_name, *sock_addr)

    return sock


def create_default_event_loop(pool_size=None, policy=event_loop_policy,
                              debug=False):
    try:
        asyncio.get_event_loop().close()
    except RuntimeError:
        pass  # event loop is not created yet

    asyncio.set_event_loop_policy(policy)

    loop = asyncio.new_event_loop()
    loop.set_debug(debug)
    asyncio.set_event_loop(loop)

    pool_size = pool_size or cpu_count()
    thread_pool = ThreadPoolExecutor(pool_size, loop=loop)
    loop.set_default_executor(thread_pool)

    return loop, thread_pool


def new_event_loop(pool_size=None,
                   policy=event_loop_policy) -> asyncio.AbstractEventLoop:
    loop, thread_pool = create_default_event_loop(pool_size, policy)
    return loop


def shield(func):
    """
    Simple and useful decorator for wrap the coroutine to `asyncio.shield`.

    >>> @shield
    ... async def non_cancelable_func():
    ...     await asyncio.sleep(1)

    """

    async def awaiter(future):
        return await future

    @wraps(func)
    def wrap(*args, **kwargs):
        return wraps(func)(awaiter)(asyncio.shield(func(*args, **kwargs)))

    return wrap


class SelectResult:
    def __init__(self, length):
        self.length = length
        self.result_idx = None
        self.is_exception = None
        self.value = None

    def set_result(self, idx, value, is_exception):
        if self.result_idx is not None:
            return

        self.value = value
        self.result_idx = idx
        self.is_exception = is_exception

    def result(self):
        if self.is_exception:
            raise self.value
        return self.value

    def done(self):
        return self.result_idx is not None

    def __iter__(self):
        for i in range(self.length - 1):
            if i == self.result_idx:
                yield self.value
            yield None


def cancel_tasks(tasks: Iterable[asyncio.Task]) -> Iterable[asyncio.Task]:
    if not tasks:
        return []

    for task in tasks:
        task.cancel()

    return tasks


async def _select_waiter(idx, awaitable, result):
    try:
        ret = await awaitable
    except asyncio.CancelledError:
        raise
    except Exception as e:
        return result.set_result(idx, e, is_exception=True)

    result.set_result(idx, ret, is_exception=False)


async def select(*awaitables, return_exceptions=False, cancel=True,
                 timeout=None, wait=True, loop=None) -> SelectResult:

    loop = loop or asyncio.get_event_loop()
    result = SelectResult(len(awaitables))

    def waiter(args):
        return _select_waiter(*args, result=result)

    ensure_future = partial(asyncio.ensure_future, loop=loop)

    _, pending = await loop.create_task(
        asyncio.wait(
            map(
                loop.create_task,
                map(waiter, enumerate(map(ensure_future, awaitables)))
            ),
            timeout=timeout, loop=loop,
            return_when=asyncio.FIRST_COMPLETED,
        ),
    )

    if cancel:
        cancelling = cancel_tasks(pending)

        cancel_task = asyncio.ensure_future(
            asyncio.gather(
                *cancelling, loop=loop, return_exceptions=True
            ),
            loop=loop
        )

        if wait:
            await cancel_task

    if result.is_exception and not return_exceptions:
        result.result()

    return result
