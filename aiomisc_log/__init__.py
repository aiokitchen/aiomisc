import logging
import logging.handlers
import os
import sys
from contextvars import ContextVar
from dataclasses import dataclass
from itertools import chain
from types import TracebackType
from typing import Any, Callable, Iterable, Optional, Type, Union

from .enum import LogFormat, LogLevel
from .formatter import (
    color_formatter, journald_formatter, json_handler, rich_formatter,
)


LOG_LEVEL: ContextVar = ContextVar("LOG_LEVEL", default=logging.INFO)
LOG_FORMAT: ContextVar = ContextVar(
    "LOG_FORMAT", default=LogFormat.default(),
)


DEFAULT_FORMAT = "%(levelname)s:%(name)s:%(message)s"


def create_logging_handler(
    log_format: LogFormat = LogFormat.color,
    date_format: Optional[str] = None, **kwargs: Any,
) -> Optional[logging.Handler]:

    LOG_FORMAT.set(log_format)

    if log_format == LogFormat.disabled:
        return None
    elif log_format == LogFormat.stream:
        handler: logging.Handler = logging.StreamHandler()
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
            **kwargs,
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


@dataclass
class UnhandledHookBase:
    logger: logging.Logger
    logger_name: str = "unhandled"
    logger_default_message: str = "Unhandled exception"


class UnhandledHook(UnhandledHookBase):
    def __init__(self, **kwargs: Any) -> None:
        logger = logging.getLogger().getChild(self.logger_name)
        logger.propagate = False
        logger.handlers.clear()
        super().__init__(logger=logger, **kwargs)

    def add_handler(self, handler: logging.Handler) -> None:
        self.logger.handlers.append(handler)


class UnhandledPythonHook(UnhandledHook):
    def __call__(
        self,
        exc_type: Type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType,
    ) -> None:
        self.logger.exception(
            self.logger_default_message,
            exc_info=(exc_type, exc_value, exc_traceback),
        )


def basic_config(
    level: Union[int, str] = LogLevel.info,
    log_format: Union[str, LogFormat] = LogFormat.color,
    handler_wrapper: HandlerWrapperType = pass_wrapper,
    handlers: Iterable[logging.Handler] = (),
    **kwargs: Any,
) -> None:

    if isinstance(level, str):
        level = LogLevel[level]

    logging.basicConfig(handlers=[], level=logging.NOTSET)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()

    if isinstance(log_format, str):
        log_format = LogFormat[log_format]

    unhandled_hook = UnhandledPythonHook()
    sys.excepthook = unhandled_hook     # type: ignore

    logging_handlers = list(
        map(
            handler_wrapper,
            filter(
                None,
                chain(
                    [create_logging_handler(log_format, **kwargs)],
                    handlers,
                ),
            ),
        ),
    )

    LOG_LEVEL.set(level)

    # noinspection PyArgumentList
    logging.basicConfig(
        level=int(level),
        handlers=logging_handlers,
    )

    for handler in logging_handlers:
        unhandled_hook.add_handler(handler)


__all__ = (
    "LogFormat",
    "LogLevel",
    "basic_config",
    "create_logging_handler",
    "LOG_FORMAT",
    "LOG_LEVEL",
)
