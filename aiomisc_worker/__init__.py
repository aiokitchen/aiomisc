import hashlib
import logging
import signal
import socket
import sys
from enum import IntEnum
from typing import Tuple, TypeVar, Union


T = TypeVar("T")
AddressType = Union[str, Tuple[str, int]]

log = logging.getLogger(__name__)

SALT_SIZE = 64
COOKIE_SIZE = 128
HASHER = hashlib.sha256


class PacketTypes(IntEnum):
    REQUEST = 0
    EXCEPTION = 1
    RESULT = 2
    CANCELLED = 3
    AUTH = 50
    AUTH_FAIL = 58
    AUTH_OK = 59
    BAD_INITIALIZER = 60
    BAD_PACKET = 254


INET_AF = socket.AF_INET6


if sys.platform in ("win32", "cygwin"):
    SIGNAL = signal.SIGBREAK      # type: ignore
    INT_SIGNAL = signal.SIGINT
else:
    SIGNAL = signal.SIGUSR2
    INT_SIGNAL = signal.SIGINT
