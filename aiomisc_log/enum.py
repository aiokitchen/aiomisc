import logging
import typing as t
from enum import Enum, IntEnum, unique


@unique
class LogFormat(IntEnum):
    stream = 0
    color = 1
    json = 2
    syslog = 3
    plain = 4
    rich = 5
    rich_tb = 6

    @classmethod
    def choices(cls) -> t.Tuple[str, ...]:
        return tuple(cls._member_names_)    # type: ignore

    @classmethod
    def default(cls) -> str:
        try:
            import rich     # noqa

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
    def choices(cls) -> t.Tuple[str, ...]:
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
