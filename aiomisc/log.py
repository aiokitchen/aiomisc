import asyncio
import logging
import logging.handlers

from typing import Union

from aiomisc.thread_pool import threaded
from aiomisc.periodic import PeriodicCallback
from prettylog import (
    color_formatter,
    create_logging_handler,
    json_formatter,
    JSONLogFormatter,
    LogFormat,
    wrap_logging_handler as _wrap_logging_handler,
)


class AsyncMemoryHandler(logging.handlers.MemoryHandler):
    flush_async = threaded(logging.handlers.MemoryHandler.flush)


def wrap_logging_handler(handler: logging.Handler,
                         loop: asyncio.AbstractEventLoop = None,
                         buffer_size: int = 1024,
                         flush_interval: float = 0.1):
    loop = loop or asyncio.get_event_loop()

    buffered_handler = _wrap_logging_handler(
        handler=handler, buffer_size=buffer_size,
        logger_class=AsyncMemoryHandler,
    )

    periodic = PeriodicCallback(buffered_handler.flush_async)
    loop.call_soon_threadsafe(periodic.start, flush_interval, loop)

    return buffered_handler


def basic_config(level: int = logging.INFO,
                 log_format: Union[str, LogFormat] = LogFormat.color,
                 buffered: bool = True, buffer_size: int = 1024,
                 flush_interval: float = 0.2, loop=None):

    if isinstance(level, str):
        level = getattr(logging, level.upper())

    logging.basicConfig()
    logger = logging.getLogger()
    logger.handlers.clear()

    if isinstance(log_format, str):
        log_format = LogFormat[log_format]

    handler = create_logging_handler(log_format)

    if buffered:
        handler = wrap_logging_handler(
            handler,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
            loop=loop,
        )

    logging.basicConfig(
        level=level,
        handlers=[handler]
    )


__all__ = (
    'basic_config',
    'wrap_logging_handler',
    'JSONLogFormatter',
    'json_formatter',
    'color_formatter',
)
