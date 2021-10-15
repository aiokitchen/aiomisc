import logging
import socket
import struct
import traceback
import uuid
from enum import IntEnum, unique
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO


@unique
class Facility(IntEnum):
    KERN = 0
    USER = 1
    MAIL = 2
    DAEMON = 3
    AUTH = 4
    SYSLOG = 5
    LPR = 6
    NEWS = 7
    UUCP = 8
    CLOCK_DAEMON = 9
    AUTHPRIV = 10
    FTP = 11
    NTP = 12
    AUDIT = 13
    ALERT = 14
    CRON = 15
    LOCAL0 = 16
    LOCAL1 = 17
    LOCAL2 = 18
    LOCAL3 = 19
    LOCAL4 = 20
    LOCAL5 = 21
    LOCAL6 = 22
    LOCAL7 = 23


class JournaldLogHandler(logging.Handler):
    LEVELS = MappingProxyType({
        logging.CRITICAL: 2,
        logging.DEBUG: 7,
        logging.FATAL: 0,
        logging.ERROR: 3,
        logging.INFO: 6,
        logging.NOTSET: 16,
        logging.WARNING: 4,
    })

    VALUE_LEN_STRUCT = struct.Struct("<Q")
    SOCKET_PATH = Path("/run/systemd/journal/socket")

    __slots__ = ("__facility", "socket", "__identifier")

    @staticmethod
    def _encode_short(key: str, value: Any) -> bytes:
        return "{}={}\n".format(key.upper(), value).encode()

    @classmethod
    def _encode_long(cls, key: str, value: bytes) -> bytes:
        length = cls.VALUE_LEN_STRUCT.pack(len(value))
        return key.upper().encode() + b"\n" + length + value + b"\n"

    @classmethod
    def pack(cls, fp: BinaryIO, key: str, value: Any) -> None:
        if not value:
            return
        elif isinstance(value, (int, float)):
            fp.write(cls._encode_short(key, value))
            return
        elif isinstance(value, bytes):
            fp.write(cls._encode_long(key, value))
            return
        elif isinstance(value, (list, tuple)):
            for idx, item in enumerate(value):
                cls.pack(fp, "{}_{}".format(key, idx), item)
            return
        elif isinstance(value, dict):
            for d_key, d_value in value.items():
                cls.pack(fp, "{}_{}".format(key, d_key), d_value)
            return

        cls.pack(fp, key, str(value).encode())
        return

    def __init__(
        self, identifier: str = None,
        facility: int = Facility.LOCAL7,
    ):
        super().__init__()
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.connect(str(self.SOCKET_PATH))
        self.__identifier = identifier
        self.__facility = int(facility)

    @staticmethod
    def _to_usec(ts: float) -> int:
        return int(ts * 1000000)

    def emit(self, record: logging.LogRecord) -> None:
        message = str(record.getMessage())

        tb_message = ""
        if record.exc_info:
            tb_message = "\n".join(
                traceback.format_exception(*record.exc_info),
            )

        message += "\n"
        message += tb_message

        ts = self._to_usec(record.created)

        hash_fields = (
            message,
            record.funcName,
            record.levelno,
            record.process,
            record.processName,
            record.levelname,
            record.pathname,
            record.name,
            record.thread,
            record.lineno,
            ts,
            tb_message,
        )

        with BytesIO() as fp:
            message_id = uuid.uuid3(
                uuid.NAMESPACE_OID, "$".join(str(x) for x in hash_fields),
            ).hex

            self.pack(fp, "message", self.format(record))
            self.pack(fp, "message_id", message_id)
            self.pack(fp, "message_raw", record.msg)
            self.pack(fp, "priority", self.LEVELS[record.levelno])
            self.pack(fp, "syslog_facility", self.__facility)
            self.pack(
                fp, "code", "{}.{}:{}".format(
                    record.module, record.funcName, record.lineno,
                ),
            )
            self.pack(
                fp, "code", {
                    "func": record.funcName,
                    "file": record.pathname,
                    "line": record.lineno,
                    "module": record.module,
                },
            )
            self.pack(fp, "logger_name", record.name)
            self.pack(fp, "pid", record.process)
            self.pack(fp, "process_name", record.processName)
            self.pack(fp, "thread_id", record.thread)
            self.pack(fp, "thread_name", record.threadName)
            self.pack(
                fp, "relative_usec", self._to_usec(record.relativeCreated),
            )

            self.pack(fp, "syslog_identifier", self.__identifier)
            self.pack(fp, "created_usec", self._to_usec(record.created))
            self.pack(fp, "arguments", record.args)
            self.pack(fp, "stack_info", record.stack_info)
            self.pack(fp, "traceback", tb_message)
            self.socket.sendall(fp.getvalue())


def journald_formatter(**_: Any) -> logging.Handler:
    handler = JournaldLogHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    return handler
