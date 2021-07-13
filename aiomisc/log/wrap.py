import asyncio
import logging
import logging.handlers
import time
from contextlib import suppress
from typing import Optional, Union

from ..thread_pool import run_in_new_thread


def _thread_flusher(
    handler: logging.handlers.MemoryHandler,
    flush_interval: Union[float, int],
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
    loop: Optional[asyncio.AbstractEventLoop] = None,
    buffer_size: int = 1024,
    flush_interval: Union[float, int] = 0.1,
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
