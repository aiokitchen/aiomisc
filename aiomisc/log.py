import asyncio
import logging
import logging.handlers
import sys
import traceback
import ujson
from enum import IntEnum
from types import MappingProxyType

from colorlog import ColoredFormatter

from .thread_pool import threaded
from .periodic import PeriodicCallback


class AsyncMemoryHandler(logging.handlers.MemoryHandler):
    flush_async = threaded(logging.handlers.MemoryHandler.flush)


class LogFormat(IntEnum):
    stream = 0
    json = 1


class JSONLogFormatter(logging.Formatter):
    LEVELS = MappingProxyType({
        logging.CRITICAL: "crit",
        logging.FATAL: "fatal",
        logging.ERROR: "error",
        logging.WARNING: "warn",
        logging.WARN: "warn",
        logging.INFO: "info",
        logging.DEBUG: "debug",
        logging.NOTSET: None,
    })

    FIELD_MAPPING = MappingProxyType({
        'filename': ('code_file', str),
        'funcName': ('code_func', str),
        'lineno': ('code_line', int),
        'module': ('code_module', str),
        'name': ('identifier', str),
        'msg': ('message_raw', str),
        'process': ('pid', int),
        'processName': ('process_name', str),
        'threadName': ('thread_name', str),
    })

    def format(self, record):
        record_dict = MappingProxyType(record.__dict__)

        data = dict(errno=0 if not record.exc_info else 255)

        for key, value in self.FIELD_MAPPING.items():
            mapping, field_type = value

            v = record_dict.get(key)

            if not isinstance(v, field_type):
                v = field_type(v)

            data[mapping] = v

        data.update(
            dict(filter(
                lambda i: (
                    not (i[0].startswith("_") or i[1] is None or i[0] in data)
                ),
                record_dict.items()
            ))
        )

        for idx, item in enumerate(data.pop('args', [])):
            data['argument_%d' % idx] = str(item)

        payload = {
            '@fields': data,
            'msg': record.getMessage(),
            'level': self.LEVELS[record.levelno]
        }

        if record.exc_info:
            payload['stackTrace'] = "\n".join(
                traceback.format_exception(*record.exc_info)
            )

        json_string = ujson.dumps(
            payload, ensure_ascii=False, escape_forward_slashes=False,
        )

        return json_string


def json_formatter(stream=None):
    stream = stream or sys.stdout
    formatter = JSONLogFormatter()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    return handler


def color_formatter(stream=None):
    stream = stream or sys.stderr
    handler = logging.StreamHandler(stream)
    handler.setFormatter(ColoredFormatter(
        "%(blue)s[T:%(threadName)s]%(reset)s "
        "%(log_color)s%(levelname)s:%(name)s%(reset)s: "
        "%(message_log_color)s%(message)s",
        datefmt=None,
        reset=True,
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
        style='%'
    ))

    return handler


def create_logging_handler(log_format: LogFormat=LogFormat.stream):
    if log_format == LogFormat.json:
        return json_formatter()
    elif log_format == LogFormat.stream:
        return color_formatter()

    raise NotImplementedError


def wrap_logging_handler(handler: logging.Handler,
                         loop: asyncio.AbstractEventLoop=None,
                         buffer_size: int = 1024,
                         flush_interval: float = 0.1):
    loop = loop or asyncio.get_event_loop()

    buffered_handler = AsyncMemoryHandler(buffer_size, target=handler)

    periodic = PeriodicCallback(buffered_handler.flush_async)
    loop.call_soon_threadsafe(periodic.start, flush_interval, loop)

    return buffered_handler


def basic_config(level: int=logging.INFO, log_format=LogFormat.stream,
                 buffered=True, buffer_size: int=1024,
                 flush_interval: float=0.2):

    logging.basicConfig()
    logger = logging.getLogger()
    logger.handlers.clear()

    if isinstance(log_format, str):
        log_format = LogFormat[log_format]

    handler = create_logging_handler(log_format)

    if buffered:
        handler = wrap_logging_handler(
            handler,
            buffer_size=buffer_size,
            flush_interval=flush_interval,
        )

    logging.basicConfig(
        level=level,
        handlers=[handler]
    )
