import atexit
import os
import sys
from contextlib import suppress
from subprocess import PIPE, Popen
from threading import Event
from time import sleep
from typing import Any, Callable, Mapping, MutableMapping, Tuple

from aiomisc_log import basic_config

from . import INT_SIGNAL, AddressType, log
from .protocol import FileIOProtocol


STOPPING = Event()


class Worker:
    def __init__(
        self, log_level: str, log_format: str, address: AddressType,
        cookie: bytes, worker_id: bytes, env: Mapping[str, str],
        initializer: Callable[..., Any],
        initializer_args: Any, initializer_kwargs: Any,
    ):
        env = dict(env)
        self.process = Popen(
            [sys.executable, "-m", "aiomisc_worker.process_inner"],
            stdin=PIPE, env=env,
        )

        assert self.process.stdin

        proto = FileIOProtocol(self.process.stdin)
        proto.send((log_level, log_format))
        proto.send(address)
        proto.send(cookie)
        proto.send(worker_id)
        proto.send((initializer, initializer_args, initializer_kwargs))
        self.process.stdin.close()
        atexit.register(self.close)

    @property
    def is_running(self) -> bool:
        return self.process.poll() is None

    def kill(self, sig: int = INT_SIGNAL) -> None:
        if not self.is_running:
            return
        os.kill(self.process.pid, sig)

    def close(self) -> None:
        with suppress(Exception):
            self.kill()
        atexit.unregister(self.close)

    def __del__(self) -> None:
        self.close()


PROCESSES: MutableMapping[Worker, bytes] = {}


def at_exit() -> None:
    processes = tuple(PROCESSES.keys())
    PROCESSES.clear()
    for process in processes:
        process.close()


def main() -> int:
    proto = FileIOProtocol(sys.stdin.buffer)

    log_level, log_format = proto.receive()
    basic_config(level=log_level, log_format=log_format)

    address: AddressType = proto.receive()
    cookie: bytes = proto.receive()
    worker_ids: Tuple[bytes, ...] = proto.receive()
    initializer, initializer_args, initializer_kwargs = proto.receive()

    sys.stdin.close()
    del proto

    env = dict(os.environ)
    env["AIOMISC_NO_PLUGINS"] = ""

    def create_worker() -> Worker:
        nonlocal env
        return Worker(
            log_level, log_format, address, cookie, worker_id, env,
            initializer, initializer_args, initializer_kwargs,
        )

    log.debug("Starting %d processes", len(worker_ids))
    for worker_id in worker_ids:
        worker = create_worker()
        PROCESSES[worker] = worker_id

    log.info("Waiting workers")

    atexit.register(at_exit)

    try:
        while True:
            for worker in tuple(PROCESSES.keys()):
                if worker.is_running:
                    continue

                worker.close()
                log.debug(
                    "Worker PID: %d exited with status %d",
                    worker.process.pid, worker.process.returncode,
                )
                worker_id = PROCESSES.pop(worker)
                worker = create_worker()
                PROCESSES[worker] = worker_id
            sleep(0.01)
    except KeyboardInterrupt:
        pass

    return 0
