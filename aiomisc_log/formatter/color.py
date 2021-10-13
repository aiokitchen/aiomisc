import logging
import sys
from typing import IO, Any

from colorlog import ColoredFormatter

from ..enum import DateFormat


def color_formatter(
    stream: IO[str] = None,
    date_format: str = None, **_: Any
) -> logging.Handler:

    date_format = (
        date_format if date_format is not None else DateFormat.color.value
    )

    stream = stream or sys.stderr
    handler = logging.StreamHandler(stream)

    fmt = (
        "%(blue)s[T:%(threadName)s]%(reset)s "
        "%(log_color)s%(levelname)s:%(name)s%(reset)s: "
        "%(message_log_color)s%(message)s"
    )

    if date_format:
        fmt = "%(bold_white)s%(bg_black)s%(asctime)s%(reset)s {0}".format(fmt)

    handler.setFormatter(
        ColoredFormatter(
            fmt,
            log_colors={
                "DEBUG": "cyan",
                "INFO": "green",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "red,bg_white",
            },
            secondary_log_colors={
                "message": {
                    "WARNING": "bold",
                    "ERROR": "bold",
                    "CRITICAL": "bold",
                },
            },
            datefmt=date_format,
            reset=True,
            style="%",
        ),
    )

    return handler
