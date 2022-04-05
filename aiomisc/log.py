import asyncio
import logging
import logging.handlers
import time
import traceback
from contextlib import suppress
from socket import socket
from typing import Any, Dict, List, Optional, Union

import aiomisc_log
from aiomisc_log.enum import LogFormat, LogLevel

from .thread_pool import run_in_new_thread


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


class UnhandledLoopHook(aiomisc_log.UnhandledHookBase):
    LOGGER_NAME = "asyncio.unhandled"

    @staticmethod
    def _fill_transport_extra(
        transport: Optional[asyncio.Transport],
        extra: Dict[str, Any],
    ) -> None:
        if transport is None:
            return

        extra["transport"] = repr(transport)

        for key in (
            "peername", "sockname", "compression",
            "cipher", "peercert", "pipe", "subprocess",
        ):
            value = transport.get_extra_info(key)
            if value:
                extra["transport_{}".format(key)] = value

    def __call__(
        self, loop: asyncio.AbstractEventLoop,
        context: Dict[str, Any],
    ) -> None:
        context = dict(context)
        message: str = context.pop("message", "unhandled loop exception")
        exception: Optional[BaseException] = context.pop("exception", None)
        future: Optional[asyncio.Future] = context.pop("future", None)
        task: Optional[asyncio.Task] = context.pop("task", None)
        handle: Optional[asyncio.Handle] = context.pop("handle", None)
        protocol: Optional[asyncio.Protocol] = context.pop("protocol", None)
        transport: Optional[asyncio.Transport] = context.pop("transport", None)
        sock: Optional[socket] = context.pop("socket", None)
        source_traceback: List[traceback.FrameSummary] = context.pop(
            "source_traceback", None,
        )

        if exception is None:
            if future is not None:
                exception = future.exception()
            elif task is not None and task.done():
                exception = task.exception()

        extra = context
        if handle is not None:
            extra["handle"] = repr(handle)
        if protocol is not None:
            extra["protocol"] = repr(protocol)
        if sock is not None:
            extra["sock"] = repr(sock)

        self._fill_transport_extra(transport, extra)
        self.logger.exception(message, exc_info=exception, extra=extra)
        if source_traceback:
            self.logger.error(
                "".join(traceback.format_list(source_traceback)),
            )


def basic_config(
    level: Union[int, str] = LogLevel.default(),
    log_format: Union[str, LogFormat] = LogFormat.default(),
    buffered: bool = True, buffer_size: int = 1024,
    flush_interval: Union[int, float] = 0.2,
    loop: asyncio.AbstractEventLoop = None,
    **kwargs: Any
) -> None:
    loop = loop or asyncio.get_event_loop()
    unhandled_hook = UnhandledLoopHook()

    def wrap_handler(handler: logging.Handler) -> logging.Handler:
        nonlocal buffer_size, buffered, loop, unhandled_hook

        unhandled_hook.set_handler(handler)

        if buffered:
            return wrap_logging_handler(
                handler=handler,
                buffer_size=buffer_size,
                flush_interval=flush_interval,
                loop=loop,
            )
        return handler

    aiomisc_log.basic_config(
        level=level,
        log_format=log_format,
        handler_wrapper=wrap_handler,
        **kwargs
    )

    loop.set_exception_handler(unhandled_hook)


__all__ = (
    "LogFormat",
    "LogLevel",
    "basic_config",
)
