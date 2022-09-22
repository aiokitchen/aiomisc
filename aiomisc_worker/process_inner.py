import sys

from aiomisc_log import basic_config

from . import AddressType
from .protocol import FileIOProtocol
from .worker import bad_initializer, worker


def worker_inner() -> None:
    proto = FileIOProtocol(sys.stdin.buffer)
    log_level, log_format = proto.receive()
    basic_config(level=log_level, log_format=log_format)

    address: AddressType = proto.receive()
    cookie: bytes = proto.receive()
    worker_id: bytes = proto.receive()
    initializer, initializer_args, initializer_kwargs = proto.receive()
    sys.stdin.close()
    del proto

    if initializer is not None:
        try:
            initializer(*initializer_args, **initializer_kwargs)
        except BaseException as e:
            bad_initializer(address, cookie, worker_id, e)
            raise SystemExit(0)

    del initializer
    del initializer_args
    del initializer_kwargs

    return worker(address, cookie, worker_id)


if __name__ == "__main__":
    worker_inner()
