import asyncio
import logging
import logging.handlers
import time
import typing as t
from contextlib import suppress
from functools import partial

import aiomisc_log
from aiomisc_log.enum import LogFormat, LogLevel

from .thread_pool import run_in_new_thread


def _thread_flusher(
    handler: logging.handlers.MemoryHandler,
    flush_interval: t.Union[float, int],
    loop: asyncio.AbstractEventLoop,
) -> None:
    def has_no_target() -> bool:
        return True

    def has_target() -> bool:
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
    loop: t.Optional[asyncio.AbstractEventLoop] = None,
    buffer_size: int = 1024,
    flush_interval: t.Union[float, int] = 0.1,
) -> logging.Handler:
    loop = loop or asyncio.get_event_loop()

    buffered_handler = logging.handlers.MemoryHandler(
        buffer_size,
        target=handler,
        flushLevel=logging.CRITICAL,
    )

    run_in_new_thread(
        _thread_flusher, args=(
            buffered_handler, flush_interval, loop,
        ), no_return=True, statistic_name="logger",
    )

    return buffered_handler


def basic_config(
    level: t.Union[int, str] = logging.INFO,
    log_format: t.Union[str, LogFormat] = LogFormat.color,
    buffered: bool = True, buffer_size: int = 1024,
    flush_interval: t.Union[int, float] = 0.2,
    loop: asyncio.AbstractEventLoop = None,
    **kwargs: t.Any
) -> None:
    wrapper = aiomisc_log.pass_wrapper

    if buffered:
        wrapper = partial(
            wrap_logging_handler,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
            loop=loop,
        )

    return aiomisc_log.basic_config(
        level=level,
        log_format=log_format,
        handler_wrapper=wrapper,
        **kwargs
    )


__all__ = (
    "LogFormat",
    "LogLevel",
    "basic_config",
)
