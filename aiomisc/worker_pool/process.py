import asyncio
import logging
import pickle
import signal
import socket
import sys
from os import urandom
from types import FrameType
from typing import Any, Tuple, Union

from aiomisc.log import basic_config
from aiomisc.worker_pool.constants import (
    HASHER, INET_AF, SALT_SIZE, SIGNAL, Header, PacketTypes,
)


def on_signal(signum: int, frame: FrameType) -> None:
    raise asyncio.CancelledError


def main() -> None:
    address: Union[str, Tuple[str, int]]
    cookie: bytes
    identity: str

    (
        address, cookie, identity, log_level, log_format,
    ) = pickle.load(sys.stdin.buffer)

    basic_config(
        level=log_level,
        log_format=log_format,
        buffered=False,
    )

    family = (
        socket.AF_UNIX if isinstance(address, str) else INET_AF
    )

    with socket.socket(family, socket.SOCK_STREAM) as sock:
        logging.debug("Connecting...")
        sock.connect(address)

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
        auth(cookie)
        del cookie

        send(PacketTypes.IDENTITY, identity)
        logging.debug("Worker ready")

        signal.signal(SIGNAL, on_signal)

        try:
            while step():
                pass
        except KeyboardInterrupt:
            return


if __name__ == "__main__":
    main()
