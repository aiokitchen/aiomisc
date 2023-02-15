import logging
import os
import sys
from enum import Enum, IntEnum, unique
from typing import Tuple


try:
    from logging_journald import check_journal_stream  # type: ignore
except ImportError:
    def check_journal_stream() -> bool:
        return False

try:
    import rich

    RICH_INSTALLED = bool(rich)
except ImportError:
    RICH_INSTALLED = False


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
        return tuple(cls._member_names_)

    @classmethod
    def default(cls) -> str:
        if check_journal_stream():
            return cls.journald.name

        if not os.isatty(sys.stderr.fileno()):
            return cls.plain.name

        if RICH_INSTALLED:
            return cls.rich.name

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
        return tuple(cls._member_names_)

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
