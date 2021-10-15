import asyncio
import logging
import pickle
import signal
import socket
import sys
from os import urandom
from types import FrameType
from typing import Any, Optional, Tuple, Union

from aiomisc_log import basic_config
from aiomisc_worker import (
    HASHER, INET_AF, SALT_SIZE, SIGNAL, Header, PacketTypes,
)


def on_signal(signum: int, frame: FrameType) -> None:
    raise asyncio.CancelledError


def main() -> Optional[int]:
    address: Union[str, Tuple[str, int]]
    cookie: bytes
    identity: str

    (
        address, cookie, identity, log_level, log_format,
    ) = pickle.load(sys.stdin.buffer)

    basic_config(level=log_level, log_format=log_format)

    family = (
        socket.AF_UNIX if isinstance(address, str) else INET_AF
    )

    with socket.socket(family, socket.SOCK_STREAM) as sock:
        logging.debug("Connecting...")
        try:
            sock.connect(address)
        except ConnectionRefusedError:
            logging.error("Failed to establish IPC.")
            return 2

        def send(packet_type: PacketTypes, data: Any) -> None:
            payload = pickle.dumps(data)
            sock.send(Header.pack(packet_type.value, len(payload)))
            sock.send(payload)

        def receive() -> Tuple[PacketTypes, Any]:
            header = sock.recv(Header.size)

            if not header:
                raise ValueError("No data")

            packet_type, payload_length = Header.unpack(header)
            payload = sock.recv(payload_length)
            return PacketTypes(packet_type), pickle.loads(payload)

        def auth(cookie: bytes) -> None:
            hasher = HASHER()
            salt = urandom(SALT_SIZE)
            send(PacketTypes.AUTH_SALT, salt)
            hasher.update(salt)
            hasher.update(cookie)
            send(PacketTypes.AUTH_DIGEST, hasher.digest())

            packet_type, value = receive()
            if packet_type == PacketTypes.AUTH_OK:
                return value

            raise RuntimeError(PacketTypes(packet_type), value)

        def step() -> bool:
            try:
                packet_type, (func, args, kwargs) = receive()
            except ConnectionResetError:
                logging.error("Pool connection closed")
                return False
            except ValueError:
                return False

            if packet_type == packet_type.REQUEST:
                response_type = PacketTypes.RESULT
                try:
                    result = func(*args, **kwargs)
                except asyncio.CancelledError:
                    logging.exception("Request cancelled for %r", func)
                    send(PacketTypes.CANCELLED, asyncio.CancelledError)
                    return True
                except Exception as e:
                    response_type = PacketTypes.EXCEPTION
                    result = e
                    logging.exception("Exception when processing request")

                send(response_type, result)
            return True

        logging.debug("Starting authorization")

        try:
            auth(cookie)
        except ConnectionResetError:
            logging.error("Failed to authorize process in pool. Exiting")
            return 3

        del cookie

        send(PacketTypes.IDENTITY, identity)
        logging.debug("Worker ready")

        signal.signal(SIGNAL, on_signal)

        try:
            while step():
                pass
            return 0
        except KeyboardInterrupt:
            return 1


if __name__ == "__main__":
    rc = main()
    exit(rc or 0)
