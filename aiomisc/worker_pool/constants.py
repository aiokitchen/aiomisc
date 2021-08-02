import hashlib
import logging
import signal
import socket
import sys
from enum import IntEnum
from struct import Struct
from typing import Tuple, TypeVar, Union


T = TypeVar("T")
AddressType = Union[str, Tuple[str, int]]

log = logging.getLogger(__name__)
Header = Struct("!BI")

SALT_SIZE = 64
COOKIE_SIZE = 128
HASHER = hashlib.sha256


class PacketTypes(IntEnum):
    REQUEST = 0
    EXCEPTION = 1
    RESULT = 2
    CANCELLED = 3
    AUTH_SALT = 50
    AUTH_DIGEST = 51
    AUTH_OK = 59
    IDENTITY = 60


INET_AF = socket.AF_INET6


if sys.platform in ("win32", "cygwin"):
    SIGNAL = signal.SIGBREAK    # type: ignore
else:
    SIGNAL = signal.SIGUSR2
