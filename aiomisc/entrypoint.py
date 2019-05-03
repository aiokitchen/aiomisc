import asyncio
import logging
from contextlib import contextmanager
from typing import Tuple, Optional, Union

from .context import Context, get_context
from .log import basic_config, LogFormat
from .service import Service
from .utils import new_event_loop, select
from .dependency import (
    get_dependencies,
    start_dependencies,
    stop_dependencies,
)


def graceful_shutdown(services: Tuple[Service, ...],
                      loop: asyncio.AbstractEventLoop,
                      exception: Optional[Exception]):

    if hasattr(loop, '_default_executor'):
        try:
            loop._default_executor.shutdown()
        except Exception:
            logging.exception("Failed to stop default executor")

    tasks = [
        asyncio.shield(loop.create_task(svc.stop(exception)), loop=loop)
        for svc in services
    ]

    if tasks:
        loop.run_until_complete(
            asyncio.wait(
                tasks, loop=loop, return_when=asyncio.ALL_COMPLETED
            )
        )

    loop.run_until_complete(stop_dependencies(loop))


@contextmanager
def entrypoint(*services: Service,
               loop: asyncio.AbstractEventLoop = None,
               pool_size: int = None,
               log_level: Union[int, str] = logging.INFO,
               log_format: Union[str, LogFormat] = 'color',
               log_buffer_size: int = 1024,
               log_flush_interval: float = 0.2,
               log_config: bool = True,
               debug: bool = False):
    """

    :param debug: set debug to event loop
    :param loop: loop
    :param services: Service instances which will be starting.
    :param pool_size: thread pool size
    :param log_level: Logging level which will be configured
    :param log_format: Logging format which will be configures
    :param log_buffer_size: Buffer size for logging
    :param log_flush_interval: interval in seconds for flushing logs
    :param log_config: if False do not configure logging
    """

    loop = loop or new_event_loop(pool_size)
    loop.set_debug(debug)

    ctx = Context(loop=loop)

    if log_config:
        basic_config(
            level=log_level,
            log_format=log_format,
            loop=loop,
            buffered=False,
        )

    async def start():
        nonlocal loop
        nonlocal services
        nonlocal log_format
        nonlocal log_level
        nonlocal log_buffer_size
        nonlocal log_flush_interval

        if log_config:
            basic_config(
                level=log_level,
                log_format=log_format,
                buffered=True,
                loop=loop,
                buffer_size=log_buffer_size,
                flush_interval=log_flush_interval,
            )

        used_deps = set()
        for svc in services:
            used_deps.update(svc.undefined_dependencies)

        await start_dependencies(used_deps, loop)

        starting = []

        async def start_service(svc: Service):
            deps = get_dependencies(svc.undefined_dependencies, loop)
            svc.__dict__.update(deps)

            await select(
                svc.start(), svc.start_event.wait(),
                cancel=False,
                loop=loop,
            )

            if not svc.start_event.is_set():
                svc.start_event.set()

        for svc in services:
            svc.set_loop(loop)
            starting.append(loop.create_task(start_service(svc)))

        await asyncio.gather(*starting, loop=loop)

    loop.run_until_complete(start())

    shutting_down = False

    try:
        yield loop
    except Exception as e:
        graceful_shutdown(services, loop, e)
        shutting_down = True
        raise
    finally:
        if not shutting_down:
            graceful_shutdown(services, loop, None)

        loop.run_until_complete(loop.shutdown_asyncgens())
        ctx.close()


__all__ = ('entrypoint', 'get_context')
