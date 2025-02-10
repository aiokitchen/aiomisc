import asyncio
import logging.handlers
import threading
import traceback
import warnings
from contextlib import suppress
from queue import Empty, Queue
from socket import socket
from typing import (
    Any, Callable, Dict, Iterable, List, Optional, Tuple, Type, Union,
)

import aiomisc_log
from aiomisc_log.enum import LogFormat, LogLevel

from .counters import Statistic


class ThreadedHandlerStatistic(Statistic):
    threads: int
    records: int
    errors: int
    flushes: int


class ThreadedHandler(logging.Handler):
    def __init__(
        self, target: logging.Handler, flush_interval: float = 0.1,
        buffered: bool = True, queue_size: int = 0,
    ):
        super().__init__()
        self._buffered = buffered
        self._target = target
        self._flush_interval = flush_interval
        self._flush_event = threading.Event()
        self._queue: Queue[Optional[logging.LogRecord]] = Queue(queue_size)
        self._close_event = threading.Event()
        self._thread = threading.Thread(target=self._in_thread, daemon=True)
        self._statistic = ThreadedHandlerStatistic()

    def start(self) -> None:
        self._statistic.threads += 1
        self._thread.start()

    def close(self) -> None:
        self._queue.put(None)
        del self._queue
        self.flush()
        self._close_event.set()
        super().close()

    def flush(self) -> None:
        self._statistic.flushes += 1
        self._flush_event.set()

    def emit(self, record: logging.LogRecord) -> None:
        if self._buffered:
            self._queue.put_nowait(record)
        else:
            self._queue.put(record)
        self._statistic.records += 1

    def _in_thread(self) -> None:
        queue = self._queue
        while not self._close_event.is_set():
            self._flush_event.wait(self._flush_interval)
            try:
                self.acquire()
                while True:
                    record = queue.get(timeout=self._flush_interval)
                    if record is None:
                        return
                    with suppress(Exception):
                        self._target.handle(record)
            except Empty:
                pass
            finally:
                self.release()
        self._statistic.threads -= 1


def suppressor(
    callback: Callable[..., None],
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[..., None]:
    def wrapper() -> None:
        with suppress(*exceptions):
            callback()
    return wrapper


def wrap_logging_handler(
    handler: logging.Handler,
    buffer_size: int = 1024,
    flush_interval: Union[float, int] = 0.1,
    loop: Optional[asyncio.AbstractEventLoop] = None,
) -> logging.Handler:
    warnings.warn("wrap_logging_handler is deprecated", DeprecationWarning)
    handler = ThreadedHandler(
        target=handler,
        queue_size=buffer_size,
        flush_interval=flush_interval,
    )
    handler.start()
    return handler


class UnhandledLoopHook(aiomisc_log.UnhandledHook):
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
                extra[f"transport_{key}"] = value

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
        source_tb: List[traceback.FrameSummary] = (
            context.pop("source_traceback", None) or []
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
        if source_tb:
            self.logger.error("".join(traceback.format_list(source_tb)))


def basic_config(
    level: Union[int, str] = LogLevel.default(),
    log_format: Union[str, LogFormat] = LogFormat.default(),
    buffered: bool = True,
    buffer_size: int = 0,
    flush_interval: Union[int, float] = 0.2,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    handlers: Iterable[logging.Handler] = (),
    **kwargs: Any,
) -> None:
    unhandled_hook = UnhandledLoopHook(logger_name="asyncio.unhandled")

    if loop is None:
        loop = asyncio.get_event_loop()

    forever_task = asyncio.gather(
        loop.create_future(), return_exceptions=True,
    )
    loop.set_exception_handler(unhandled_hook)

    log_handlers = []

    for user_handler in handlers:
        handler = ThreadedHandler(
            buffered=buffered,
            flush_interval=flush_interval,
            queue_size=buffer_size,
            target=user_handler,
        )
        unhandled_hook.add_handler(handler)
        forever_task.add_done_callback(lambda _: handler.close())
        log_handlers.append(handler)
        handler.start()

    aiomisc_log.basic_config(
        level=level, log_format=log_format, handlers=log_handlers, **kwargs,
    )


__all__ = (
    "LogFormat",
    "LogLevel",
    "basic_config",
    "ThreadedHandler",
)
