import asyncio
import logging
from contextlib import contextmanager
from typing import Tuple, Optional, Union

from .log import basic_config, LogFormat
from .service import Service
from .utils import new_event_loop


async def graceful_shutdown(services: Tuple[Service, ...],
                            loop: asyncio.AbstractEventLoop,
                            exception: Optional[Exception]):
    tasks = [
        asyncio.shield(loop.create_task(svc.stop(exception)), loop=loop)
        for svc in services
    ]

    if not tasks:
        return

    await asyncio.wait(tasks, loop=loop, return_when=asyncio.ALL_COMPLETED)


@contextmanager
def entrypoint(*services: Service,
               loop: asyncio.AbstractEventLoop = None,
               pool_size: int = None,
               log_level: Union[int, str] = logging.INFO,
               log_format: Union[str, LogFormat] = 'color',
               log_buffer_size: int = 1024,
               log_flush_interval: float = 0.2):

    loop = loop or new_event_loop(pool_size)

    basic_config(
        level=log_level,
        log_format=log_format,
        buffered=False,
    )

    async def start():
        nonlocal loop
        nonlocal services
        nonlocal log_format
        nonlocal log_level
        nonlocal log_buffer_size
        nonlocal log_flush_interval

        basic_config(
            level=log_level,
            log_format=log_format,
            buffered=True,
            loop=loop,
            buffer_size=log_buffer_size,
            flush_interval=log_flush_interval,
        )

        starting = []

        for svc in services:
            svc.set_loop(loop)

            starting.append(loop.create_task(svc.start()))

        await asyncio.gather(*starting, loop=loop)

    loop.run_until_complete(start())
    try:
        yield loop
    except Exception as e:
        loop.run_until_complete(graceful_shutdown(services, loop, e))
    else:
        loop.run_until_complete(graceful_shutdown(services, loop, None))
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
