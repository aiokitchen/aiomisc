import logging
import socket
import struct
import traceback
import uuid
from enum import IntEnum, unique
from io import BytesIO
from pathlib import Path
from types import MappingProxyType
from typing import Any, BinaryIO, Mapping


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

    @classmethod
    def pack(cls, fp: BinaryIO, key: str, value: Any) -> None:
        value_bytes = str(value).encode()
        fp.write(key.upper().encode())
        fp.write(b"\n")
        fp.write(cls.VALUE_LEN_STRUCT.pack(len(value_bytes)))
        fp.write(value_bytes)
        fp.write(b"\n")

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
    def _to_microsecond(ts: float) -> int:
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

        ts = self._to_microsecond(record.created)

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
            self.pack(fp, "priority", self.LEVELS[record.levelno])
            self.pack(fp, "syslog_facility", self.__facility)
            self.pack(fp, "code_file", record.filename)
            self.pack(fp, "code_line", record.lineno)
            self.pack(fp, "code_func", record.funcName)
            self.pack(fp, "code_module", record.module)
            self.pack(fp, "logger_name", record.name)
            self.pack(fp, "pid", record.process)
            self.pack(fp, "proccess_name", record.processName)
            self.pack(fp, "thread_name", record.threadName)
            self.pack(fp, "message_id", message_id)
            self.pack(
                fp, "relative_ts",
                self._to_microsecond(record.relativeCreated),
            )

            if self.__identifier:
                self.pack(fp, "syslog_identifier", self.__identifier)

            if record.msg:
                self.pack(fp, "message_raw", record.msg)

            if isinstance(record.args, Mapping):
                for key, value in record.args.items():
                    self.pack(fp, "argument_%s" % key, value)
            else:
                for idx, item in enumerate(record.args):
                    self.pack(fp, "argument_%d" % idx, item)

            if tb_message:
                self.pack(fp, "traceback", tb_message)

            self.socket.sendall(fp.getvalue())


def journald_formatter(**_: Any) -> logging.Handler:
    handler = JournaldLogHandler()
    formatter = logging.Formatter("%(message)s")
    handler.setFormatter(formatter)
    return handler
