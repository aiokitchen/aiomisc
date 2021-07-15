import json
import logging
import sys
import traceback
import typing as t
from types import MappingProxyType


JSONObjType = t.Dict[str, t.Any]
DumpsType = t.Callable[[JSONObjType, t.Any], str]


def _dump_json(obj: JSONObjType, *args: t.Any, **kwargs: t.Any) -> str:
    kwargs["default"] = repr
    kwargs["ensure_ascii"] = False
    return json.dumps(obj, *args, **kwargs)


class JSONLogFormatter(logging.Formatter):

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
        "filename": ("code_file", str),
        "funcName": ("code_func", str),
        "lineno": ("code_line", int),
        "module": ("code_module", str),
        "name": ("identifier", str),
        "msg": ("message_raw", str),
        "process": ("pid", int),
        "processName": ("process_name", str),
        "threadName": ("thread_name", str),
    })

    def __init__(
        self, fmt: str = None, datefmt: str = None,
        style: str = "%", dumps: DumpsType = _dump_json,
    ):
        super().__init__(
            datefmt=datefmt if datefmt is not Ellipsis else None,
            fmt=fmt, style=style,
        )
        self.dumps = dumps

    def format(self, record: logging.LogRecord) -> str:
        record_dict = MappingProxyType(record.__dict__)

        data = dict(
            errno=0 if not record.exc_info else 255,
        )    # type: t.Dict[str, t.Any]

        for key, value in self.FIELD_MAPPING.items():
            mapping, field_type = value

            v = record_dict.get(key)

            if not isinstance(v, field_type):
                v = field_type(v)

            data[mapping] = v

        for key in record_dict:
            if key in data:
                continue
            elif key in self.FIELD_MAPPING:
                continue
            elif key[0] == "_":
                continue

            record_value = record_dict[key]    # type: t.Any

            if record_value is None:
                continue

            data[key] = record_value

        args = data.pop("args", [])     # type: t.List[t.Any]

        for idx, item in enumerate(args):
            data["argument_%d" % idx] = str(item)

        payload = {
            "@fields": data,
            "msg": self.formatMessage(record),
            "level": self.LEVELS[record.levelno],
        }   # type: JSONObjType

        if self.datefmt:
            payload["@timestamp"] = self.formatTime(record, self.datefmt)

        if record.exc_info:
            payload["stackTrace"] = self.formatException(record.exc_info)

        return self.dumps(payload)      # type: ignore

    def formatMessage(self, record: logging.LogRecord) -> str:
        return record.getMessage()

    def formatException(self, exc_info: t.Any) -> str:
        return "\n".join(traceback.format_exception(*exc_info))

    def formatTime(     # type: ignore
        self, record: logging.LogRecord, datefmt: str = None,
    ) -> t.Union[int, str]:
        if datefmt == "%s":
            return record.created   # type: ignore
        return super().formatTime(record, datefmt=datefmt)


def json_handler(
    stream: t.IO[str] = None,
    date_format: str = None,
    **kwargs: t.Any
) -> logging.Handler:
    log_stream = stream or sys.stdout       # type: t.IO[str]
    formatter = JSONLogFormatter(datefmt=date_format, **kwargs)
    handler = logging.StreamHandler(log_stream)
    handler.setFormatter(formatter)
    return handler
