import logging
import sys

from colorlog import ColoredFormatter
from aiomisc.log.enum import DateFormat


def color_formatter(stream=None, date_format=..., **_) -> logging.Handler:

    date_format = (
        date_format if date_format is not Ellipsis else DateFormat.color.value
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
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'red,bg_white',
            },
            secondary_log_colors={
                'message': {
                    'WARNING': 'bold',
                    'ERROR': 'bold',
                    'CRITICAL': 'bold',
                },
            },
            datefmt=date_format,
            reset=True,
            style='%',
        )
    )

    return handler
