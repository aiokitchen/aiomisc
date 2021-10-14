import asyncio
import logging
import logging.handlers
import time
from contextlib import suppress
from functools import partial
from socket import socket
from typing import Any, Dict, Optional, Union

import aiomisc_log
from aiomisc_log.enum import LogFormat, LogLevel

from .thread_pool import run_in_new_thread


try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


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


class AsyncioExceptionContext(TypedDict):
    message: str
    exception: Optional[BaseException]
    future: Optional[asyncio.Future]
    task: Optional[asyncio.Task]
    handle: Optional[asyncio.Handle]
    protocol: Optional[asyncio.Protocol]
    transport: Optional[asyncio.Transport]
    socket: Optional[socket]


class UnhandledLoopHook(aiomisc_log.UnhandledHookBase):
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
        context: AsyncioExceptionContext,
    ) -> None:
        message: str = context.get("message", "unhandled loop exception")
        exception: Optional[BaseException] = context.get("exception")
        future: Optional[asyncio.Future] = context.get("future")
        task: Optional[asyncio.Task] = context.get("task")
        handle: Optional[asyncio.Handle] = context.get("handle")
        protocol: Optional[asyncio.Protocol] = context.get("protocol")
        transport: Optional[asyncio.Transport] = context.get("transport")
        sock: Optional[socket] = context.get("socket")

        if exception is None:
            if future is not None:
                exception = future.exception()
            elif task is not None:
                exception = task.exception()

        extra = {}
        if handle is not None:
            extra["handle"] = repr(handle)
        if protocol is not None:
            extra["protocol"] = repr(protocol)
        if sock is not None:
            extra["sock"] = repr(sock)

        self._fill_transport_extra(transport, extra)
        self.logger.exception(message, exc_info=exception, extra=extra)


def basic_config(
    level: Union[int, str] = LogLevel.default(),
    log_format: Union[str, LogFormat] = LogFormat.default(),
    buffered: bool = True, buffer_size: int = 1024,
    flush_interval: Union[int, float] = 0.2,
    loop: asyncio.AbstractEventLoop = None,
    **kwargs: Any
) -> None:
    wrapper = aiomisc_log.pass_wrapper

    loop = loop or asyncio.get_event_loop()

    if buffered:
        wrapper = partial(
            wrap_logging_handler,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
            loop=loop,
        )

    loop.set_exception_handler(UnhandledLoopHook())     # type: ignore

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
