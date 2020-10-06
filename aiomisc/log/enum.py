import logging
from enum import IntEnum, Enum, unique


@unique
class LogFormat(IntEnum):
    stream = 0
    color = 1
    json = 2
    syslog = 3

    @classmethod
    def choices(cls):
        return tuple(cls._member_names_)


class LogLevel(IntEnum):
    critical = logging.CRITICAL
    error = logging.ERROR
    warning = logging.WARNING
    info = logging.INFO
    debug = logging.DEBUG
    notset = logging.NOTSET

    @classmethod
    def choices(cls):
        return tuple(cls._member_names_)


class DateFormat(Enum):
    color = '%Y-%m-%d %H:%M:%S'
    stream = '[%Y-%m-%d %H:%M:%S]'
    # Optimization: float value will be returned
    json = '%s'
    syslog = None
