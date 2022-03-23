import asyncio
import hashlib
import hmac
import logging
import os
import signal
import socket
import sys
from types import TracebackType
from typing import Any, Optional, Type

from . import SIGNAL, AddressType, PacketTypes
from .protocol import ADDRESS_FAMILY, SocketIOProtocol


def execute(protocol: SocketIOProtocol) -> None:
    pid = os.getpid()
    try:
        packet_type, func, args, kwargs = protocol.receive()
        logging.debug(
            "Worker PID: %d got task %r", pid, func, extra={"pid": pid},
        )
    except ConnectionError:
        raise

    if packet_type != packet_type.REQUEST:
        raise RuntimeError("Unexpected request")

    try:
        protocol.send((
            PacketTypes.RESULT,
            func(*args, **kwargs),
        ))
    except asyncio.CancelledError:
        logging.exception(
            "Request cancelled for %r", func, extra={"pid": pid},
        )
        protocol.send((
            PacketTypes.CANCELLED,
            asyncio.CancelledError,
        ))
    except (ConnectionError, ConnectionResetError):
        logging.warning(
            "IPC connection error, worker PID: %d exiting.", pid,
            extra={"pid": pid},
        )
        raise
    except Exception as e:
        logging.exception("Exception when processing request")
        protocol.send((
            PacketTypes.EXCEPTION, e,
        ))


def on_cancel_signal(*_: Any) -> None:
    raise asyncio.CancelledError


signal.signal(SIGNAL, on_cancel_signal)


def on_exception(
    exc_type: Optional[Type[BaseException]],
    exc_value: Optional[BaseException],
    exc_tb: Optional[TracebackType],
) -> None:
    if exc_type is None or exc_value is None or exc_tb is None:
        return
    pid = os.getpid()
    logging.exception(
        "Unhandled exception in worker PID: %d",
        pid, exc_info=(exc_type, exc_value, exc_tb), extra={"pid": pid},
    )


def worker(address: AddressType, cookie: bytes, worker_id: bytes) -> None:
    sys.excepthook = on_exception

    with socket.socket(ADDRESS_FAMILY, socket.SOCK_STREAM) as sock:
        try:
            sock.connect(address)
            proto = SocketIOProtocol(sock)
            proto.send((
                PacketTypes.AUTH,
                worker_id,
                hmac.HMAC(
                    cookie, worker_id, digestmod=hashlib.sha256,
                ).digest(),
                os.getpid(),
            ))

            response = proto.receive()

            if response != PacketTypes.AUTH_OK:
                raise RuntimeError(
                    f"Failed to authorize worker on {address!r}",
                )

            while True:
                execute(proto)
        except ConnectionError:
            return


def bad_initializer(
    address: AddressType, cookie: bytes, worker_id: bytes, exc: BaseException,
) -> None:
    with socket.socket(ADDRESS_FAMILY, socket.SOCK_STREAM) as sock:
        sock.connect(address)
        proto = SocketIOProtocol(sock)
        proto.send((
            PacketTypes.BAD_INITIALIZER,
            worker_id,
            hmac.HMAC(cookie, worker_id, digestmod=hashlib.sha256).digest(),
            os.getpid(),
        ))
        proto.send((PacketTypes.EXCEPTION, exc))
