import atexit
import gc
import os
import signal
import sys
from contextlib import suppress
from threading import Event, Lock
from typing import Any, MutableMapping, Optional, Tuple

from aiomisc_log import basic_config

from . import INT_SIGNAL, AddressType, log
from .protocol import FileIOProtocol
from .worker import bad_initializer, worker


PROCESSES: MutableMapping[int, bytes] = dict()
STOPPING = Event()
EXIT_LOCK = Lock()


def at_exit() -> None:
    global PROCESSES

    with EXIT_LOCK:
        pids = tuple(PROCESSES.keys())
        PROCESSES.clear()

    for pid in pids:
        log.debug("Terminating PID: %d", pid)
        with suppress(Exception):
            os.kill(pid, signal.SIGTERM)


def handle_interrupt(*_: Any) -> None:
    STOPPING.set()
    raise KeyboardInterrupt


DEFAULT_SIGNAL_HANDLER = signal.getsignal(INT_SIGNAL)


def fork(worker_id: bytes, cookie: bytes, address: AddressType) -> None:
    global PROCESSES

    gc.disable()
    pid = os.fork()
    gc.enable()

    if pid != 0:
        # In master process
        PROCESSES[pid] = worker_id
        log.debug("Started child process PID: %d", pid)
        return

    # In child process
    PROCESSES = {}
    signal.signal(INT_SIGNAL, DEFAULT_SIGNAL_HANDLER)
    worker(address, cookie, worker_id)
    raise SystemExit(0)


def main() -> int:
    global STOPPING

    proto_stdin = FileIOProtocol(sys.stdin.buffer)

    log_level, log_format = proto_stdin.receive()
    basic_config(level=log_level, log_format=log_format)

    address: AddressType = proto_stdin.receive()
    cookie: bytes = proto_stdin.receive()
    worker_ids: Tuple[bytes, ...] = proto_stdin.receive()
    initializer, initializer_args, initializer_kwargs = proto_stdin.receive()
    worker_id: Optional[bytes]

    def run_initializer() -> None:
        # Saving the initializer result and prevent freeing it
        if not initializer:
            return

        # noinspection PyBroadException
        try:
            initializer(*initializer_args, **initializer_kwargs)
        except BaseException as e:
            log.exception(
                "WorkerPool initializer %r has been failed", initializer,
            )
            bad_initializer(address, cookie, worker_ids[0], e)
            raise SystemExit(0)

    sys.stdin.close()
    del proto_stdin

    run_initializer()

    signal.signal(INT_SIGNAL, handle_interrupt)
    atexit.register(at_exit)

    log.debug("Forking %d processes", len(worker_ids))
    for worker_id in worker_ids:
        fork(worker_id, cookie, address)

    log.debug("Waiting workers")
    while not STOPPING.is_set():
        pid, status = os.wait()
        log_func = log.debug if status == 0 else log.warning
        log_func("Worker PID: %d exited with status %d", pid, status)

        if status == 0:
            continue
        worker_id = PROCESSES.pop(pid, None)
        if worker_id is None:
            continue
        fork(worker_id, cookie, address)
    return 0
