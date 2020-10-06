import asyncio
import logging
import os
import sys
from typing import Union, Optional

from .enum import LogFormat, LogLevel
from .formatter import json_formatter, color_formatter
from .wrap import wrap_logging_handler

DEFAULT_FORMAT = '%(levelname)s:%(name)s:%(message)s'


def create_logging_handler(log_format: LogFormat = LogFormat.color,
                           date_format=None, **kwargs):

    if log_format == LogFormat.stream:
        handler = logging.StreamHandler()
        if date_format and date_format is not Ellipsis:
            formatter = logging.Formatter(
                "%(asctime)s " + DEFAULT_FORMAT, datefmt=date_format
            )
        else:
            formatter = logging.Formatter(DEFAULT_FORMAT)

        handler.setFormatter(formatter)
        return handler
    elif log_format == LogFormat.json:
        return json_formatter(date_format=date_format, **kwargs)
    elif log_format == LogFormat.color:
        return color_formatter(date_format=date_format, **kwargs)
    elif log_format == LogFormat.syslog:
        if date_format:
            sys.stderr.write("Can not apply \"date_format\" for syslog\n")
            sys.stderr.flush()

        formatter = logging.Formatter("%(message)s")

        if os.path.exists('/dev/log'):
            handler = logging.handlers.SysLogHandler(address='/dev/log')
        else:
            handler = logging.handlers.SysLogHandler()

        handler.setFormatter(formatter)
        return handler

    raise NotImplementedError


def basic_config(
    level: int = logging.INFO,
    log_format: Union[str, LogFormat] = LogFormat.color,
    buffered: bool = True, buffer_size: int = 1024,
    flush_interval: Union[int, float] = 0.2,
    loop: Optional[asyncio.AbstractEventLoop] = None,
    **kwargs
):

    if isinstance(level, str):
        level = LogLevel[level]

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
        level=int(level),
        handlers=[handler],
    )
