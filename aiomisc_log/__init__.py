import logging
import logging.handlers
import os
import sys
from types import TracebackType
from typing import Any, Callable, Optional, Type, Union

from .enum import LogFormat, LogLevel
from .formatter import (
    color_formatter, journald_formatter, json_handler, rich_formatter,
)


LOG_LEVEL: Optional[Any] = None
LOG_FORMAT: Optional[Any] = None

try:
    import contextvars
    LOG_LEVEL = contextvars.ContextVar("LOG_LEVEL", default=logging.INFO)
    LOG_FORMAT = contextvars.ContextVar("LOG_FORMAT", default=LogFormat.color)
except ImportError:
    pass


DEFAULT_FORMAT = "%(levelname)s:%(name)s:%(message)s"


def create_logging_handler(
    log_format: LogFormat = LogFormat.color,
    date_format: str = None, **kwargs: Any
) -> logging.Handler:

    if LOG_FORMAT is not None:
        LOG_FORMAT.set(log_format)

    handler: logging.Handler

    if log_format == LogFormat.stream:
        handler = logging.StreamHandler()
        if date_format and date_format is not Ellipsis:
            formatter = logging.Formatter(
                "%(asctime)s " + DEFAULT_FORMAT, datefmt=date_format,
            )
        else:
            formatter = logging.Formatter(DEFAULT_FORMAT)

        handler.setFormatter(formatter)
        return handler
    elif log_format == LogFormat.json:
        return json_handler(date_format=date_format, **kwargs)
    elif log_format == LogFormat.color:
        return color_formatter(date_format=date_format, **kwargs)
    elif log_format == LogFormat.journald:
        return journald_formatter()
    elif log_format == LogFormat.rich:
        return rich_formatter(date_format=date_format, **kwargs)
    elif log_format == LogFormat.rich_tb:
        return rich_formatter(
            date_format=date_format,
            rich_tracebacks=True,
            **kwargs
        )
    elif log_format == LogFormat.syslog:
        if date_format:
            sys.stderr.write("Can not apply \"date_format\" for syslog\n")
            sys.stderr.flush()

        formatter = logging.Formatter("%(message)s")

        if os.path.exists("/dev/log"):
            handler = logging.handlers.SysLogHandler(address="/dev/log")
        else:
            handler = logging.handlers.SysLogHandler()

        handler.setFormatter(formatter)
        return handler
    elif log_format == LogFormat.plain:
        handler = logging.StreamHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        return handler

    raise NotImplementedError


HandlerWrapperType = Callable[[logging.Handler], logging.Handler]


def pass_wrapper(handler: logging.Handler) -> logging.Handler:
    return handler


class UnhandledHookBase:
    __slots__ = "logger",

    LOGGER_NAME: str = "unhandled"
    logger: logging.Logger

    def __init__(self) -> None:
        self.logger = logging.getLogger().getChild(self.LOGGER_NAME)
        self.logger.propagate = False

    def set_handler(self, handler: logging.Handler) -> None:
        self.logger.handlers.clear()
        self.logger.handlers.append(handler)


class UnhandledHook(UnhandledHookBase):
    MESSAGE: str = "Unhandled exception"

    def __call__(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType,
    ) -> None:
        self.logger.exception(
            self.MESSAGE, exc_info=(exc_type, exc_value, exc_traceback),
        )


def basic_config(
    level: Union[int, str] = logging.INFO,
    log_format: Union[str, LogFormat] = LogFormat.color,
    handler_wrapper: HandlerWrapperType = pass_wrapper,
    **kwargs: Any
) -> None:

    if isinstance(level, str):
        level = LogLevel[level]

    logging.basicConfig()
    logger = logging.getLogger()
    logger.handlers.clear()

    if isinstance(log_format, str):
        log_format = LogFormat[log_format]

    raw_handler = create_logging_handler(log_format, **kwargs)
    unhandled_hook = UnhandledHook()
    sys.excepthook = unhandled_hook

    handler = handler_wrapper(raw_handler)

    if LOG_LEVEL is not None:
        LOG_LEVEL.set(level)

    # noinspection PyArgumentList
    logging.basicConfig(
        level=int(level),
        handlers=[handler],
    )

    unhandled_hook.set_handler(raw_handler)


__all__ = (
    "LogFormat",
    "LogLevel",
    "basic_config",
)
