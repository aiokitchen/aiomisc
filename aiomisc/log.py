import asyncio
import logging
import logging.handlers
import time
from contextlib import suppress
from threading import Thread

from typing import Union

from prettylog import (
    color_formatter,
    create_logging_handler,
    json_formatter,
    JSONLogFormatter,
    LogFormat,
    wrap_logging_handler as _wrap_logging_handler,
)


def _thread_flusher(handler: logging.handlers.MemoryHandler,
                    flush_interval: Union[float, int],
                    loop: asyncio.AbstractEventLoop):
    while not loop.is_closed():
        if handler.buffer:
            with suppress(Exception):
                handler.flush()

        time.sleep(flush_interval)


def wrap_logging_handler(handler: logging.Handler,
                         loop: asyncio.AbstractEventLoop = None,
                         buffer_size: int = 1024,
                         flush_interval: float = 0.1):
    loop = loop or asyncio.get_event_loop()

    buffered_handler = _wrap_logging_handler(
        handler=handler, buffer_size=buffer_size
    )

    flusher = Thread(
        target=_thread_flusher,
        args=(buffered_handler, flush_interval, loop),
        name="Log flusher"
    )

    flusher.daemon = True

    loop.call_soon_threadsafe(flusher.start)
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
    'color_formatter',
    'json_formatter',
    'JSONLogFormatter',
    'LogFormat',
    'wrap_logging_handler',
)
