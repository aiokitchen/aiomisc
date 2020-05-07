import asyncio
import logging
import logging.handlers
import time
from contextlib import suppress
from typing import Union

from prettylog import (
    JSONLogFormatter, LogFormat, color_formatter, create_logging_handler,
    json_formatter,
)
from prettylog import wrap_logging_handler as _wrap_logging_handler

from .thread_pool import run_in_new_thread


def _thread_flusher(
    handler: logging.handlers.MemoryHandler,
    flush_interval: Union[float, int],
    loop: asyncio.AbstractEventLoop,
):
    def has_no_target():
        return True

    def has_target():
        return bool(handler.target)

    is_target = has_no_target

    if isinstance(handler, logging.handlers.MemoryHandler):
        is_target = has_target

    while not loop.is_closed() and is_target():
        with suppress(Exception):
            if handler.buffer:
                handler.flush()

        time.sleep(flush_interval)


def wrap_logging_handler(
    handler: logging.Handler,
    loop: asyncio.AbstractEventLoop = None,
    buffer_size: int = 1024,
    flush_interval: float = 0.1,
):
    loop = loop or asyncio.get_event_loop()

    buffered_handler = _wrap_logging_handler(
        handler=handler, buffer_size=buffer_size,
    )

    run_in_new_thread(
        _thread_flusher, args=(
            buffered_handler, flush_interval, loop,
        ), no_return=True,
    )

    return buffered_handler


def basic_config(
    level: int = logging.INFO,
    log_format: Union[str, LogFormat] = LogFormat.color,
    buffered: bool = True, buffer_size: int = 1024,
    flush_interval: float = 0.2, loop=None, **kwargs
):

    if isinstance(level, str):
        level = getattr(logging, level.upper())

    logging.basicConfig()
    logger = logging.getLogger()
    logger.handlers.clear()

    if isinstance(log_format, str):
        log_format = LogFormat[log_format]

    handler = create_logging_handler(log_format, **kwargs)

    if buffered:
        handler = wrap_logging_handler(
            handler,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
            loop=loop,
        )

    logging.basicConfig(
        level=level,
        handlers=[handler],
    )


__all__ = (
    "basic_config",
    "color_formatter",
    "json_formatter",
    "JSONLogFormatter",
    "LogFormat",
    "wrap_logging_handler",
)
