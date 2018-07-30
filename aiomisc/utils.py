import asyncio
import itertools
import logging.handlers
import socket
from multiprocessing import cpu_count
from typing import Any, Coroutine, Iterable, List, Tuple

import uvloop

from aiomisc.thread_pool import ThreadPoolExecutor


log = logging.getLogger(__name__)


def chunk_list(iterable: Iterable[Any], size: int):
    iterable = iter(iterable)

    item = list(itertools.islice(iterable, size))
    while item:
        yield item
        item = list(itertools.islice(iterable, size))


OptionsType = Iterable[Tuple[int, int, int]]


def bind_socket(*args, address: str, port: int, options: OptionsType = (),
                reuse_addr: bool = True, reuse_port: bool = False,
                proto_name: str = 'tcp'):

    if not args:
        if ':' in address:
            args = (socket.AF_INET6, socket.SOCK_STREAM)
        else:
            args = (socket.AF_INET, socket.SOCK_STREAM)

    sock = socket.socket(*args)
    sock.setblocking(0)

    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, int(reuse_addr))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, int(reuse_port))

    for level, option, value in options:
        sock.setsockopt(level, option, value)

    sock.bind((address, port))
    sock_addr = sock.getsockname()[:2]

    if sock.family == socket.AF_INET6:
        log.info('Listening %s://[%s]:%s', proto_name, *sock_addr)
    else:
        log.info('Listening %s://%s:%s', proto_name, *sock_addr)

    return sock


def new_event_loop(pool_size=None) -> asyncio.AbstractEventLoop:
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())

    pool_size = pool_size or cpu_count()

    try:
        asyncio.get_event_loop().close()
    except RuntimeError:
        pass  # event loop is not created yet

    loop = asyncio.new_event_loop()
    thread_pool = ThreadPoolExecutor(pool_size, loop=loop)

    loop.set_default_executor(thread_pool)

    asyncio.set_event_loop(loop)

    return loop


# Type hint should be here for pylama's checks
_TASKS_LIST = List[asyncio.Task]


def wait_for(*coroutines: Tuple[Coroutine, ...],
             raise_first: bool = True,
             cancel: bool = True,
             loop: asyncio.AbstractEventLoop = None):

    tasks = list()                           # type: _TASKS_LIST
    loop = loop or asyncio.get_event_loop()  # type: asyncio.AbstractEventLoop
    result_future = loop.create_future()     # type: asyncio.Future
    waiting = len(coroutines)

    def cancel_pending():
        nonlocal result_future
        nonlocal tasks

        for t in tasks:
            if t.done():
                continue

            t.cancel()

    def raise_first_exception(exc: Exception):
        nonlocal result_future
        nonlocal tasks

        if result_future.done():
            return

        result_future.set_exception(exc)

    def return_result():
        nonlocal result_future
        nonlocal tasks

        if result_future.done():
            return

        results = []

        for task in tasks:
            exc = task.exception()

            results.append(task.result() if exc is None else exc)

        result_future.set_result(results)

    def done_callback(t: asyncio.Future):
        nonlocal tasks
        nonlocal result_future
        nonlocal waiting

        waiting -= 1

        exc = t.exception()

        if t.cancelled() or exc is None:
            if waiting == 0:
                return_result()

            return

        if raise_first:
            raise_first_exception(exc)

        if waiting == 0:
            return_result()

    for coroutine in coroutines:
        task = loop.create_task(coroutine)
        task.add_done_callback(done_callback)
        tasks.append(task)

    async def run():
        nonlocal result_future

        try:
            return await result_future
        finally:
            if cancel:
                cancel_pending()

    return run()
