import json
import logging
import sys
import traceback
from types import MappingProxyType
from typing import Union


def _dump_json(*args, **kwargs):
    return json.dumps(*args, **kwargs, default=repr)


class JSONLogFormatter(logging.Formatter):
    JSON_DUMPS = _dump_json

    LEVELS = MappingProxyType({
        logging.CRITICAL: "crit",
        logging.FATAL: "fatal",
        logging.ERROR: "error",
        logging.WARNING: "warn",
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

    def __init__(self, fmt=None, datefmt=None, style='%', dumps=JSON_DUMPS):
        super().__init__(
            datefmt=datefmt if datefmt is not Ellipsis else None,
            fmt=fmt, style=style
        )
        self.dumps = dumps

    def format(self, record: logging.LogRecord):
        record_dict = MappingProxyType(record.__dict__)

        data = dict(errno=0 if not record.exc_info else 255)

        for key, value in self.FIELD_MAPPING.items():
            mapping, field_type = value

            v = record_dict.get(key)

            if not isinstance(v, field_type):
                v = field_type(v)

            data[mapping] = v

        for key in record_dict:
            if key in data:
                continue
            elif key[0] == "_":
                continue

            value = record_dict[key]

            if value is None:
                continue

            data[key] = value

        for idx, item in enumerate(data.pop('args', [])):
            data['argument_%d' % idx] = str(item)

        payload = {
            '@fields': data,
            'msg': self.formatMessage(record),
            'level': self.LEVELS[record.levelno],
        }

        if self.datefmt:
            payload['@timestamp'] = self.formatTime(record, self.datefmt)

        if record.exc_info:
            payload['stackTrace'] = self.formatException(record.exc_info)

        return self.dumps(payload, ensure_ascii=False)

    def formatMessage(self, record: logging.LogRecord) -> str:
        return record.getMessage()

    def formatException(self, exc_info) -> str:
        return "\n".join(traceback.format_exception(*exc_info))

    def formatTime(self, record, datefmt=None) -> Union[int, str]:
        if datefmt == '%s':
            return record.created
        return super().formatTime(record, datefmt=datefmt)


def json_formatter(stream=None, date_format=None, **kwargs):
    stream = stream or sys.stdout
    formatter = JSONLogFormatter(datefmt=date_format, **kwargs)
    handler = logging.StreamHandler(stream)
    handler.setFormatter(formatter)
    return handler
