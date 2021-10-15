import logging
import os
import sys
from enum import Enum, IntEnum, unique
from typing import Tuple


@unique
class LogFormat(IntEnum):
    stream = 0
    color = 1
    json = 2
    syslog = 3
    plain = 4
    journald = 5
    rich = 6
    rich_tb = 7

    @classmethod
    def choices(cls) -> Tuple[str, ...]:
        return tuple(cls._member_names_)    # type: ignore

    @classmethod
    def default(cls) -> str:
        if not os.isatty(sys.stderr.fileno()):
            return cls.plain.name

        journal_stream = os.getenv("JOURNAL_STREAM", "")
        if journal_stream:
            st_dev, st_ino = map(int, journal_stream.split(":", 1))
            stat = os.stat(sys.stderr.fileno())
            if stat.st_ino == st_ino and stat.st_dev == st_dev:
                return cls.journald.name
        try:
            import rich  # noqa

            return cls.rich.name
        except ImportError:
            return cls.color.name


class LogLevel(IntEnum):
    critical = logging.CRITICAL
    error = logging.ERROR
    warning = logging.WARNING
    info = logging.INFO
    debug = logging.DEBUG
    notset = logging.NOTSET

    @classmethod
    def choices(cls) -> Tuple[str, ...]:
        return tuple(cls._member_names_)    # type: ignore

    @classmethod
    def default(cls) -> str:
        return cls.info.name


class DateFormat(Enum):
    color = "%Y-%m-%d %H:%M:%S"
    stream = "[%Y-%m-%d %H:%M:%S]"

    # Optimization: special value ``%s`` date will
    # not formatted just returns record created time
    json = "%s"
    syslog = None
    rich = "[%X]"
