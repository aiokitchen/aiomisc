import asyncio
import hashlib
import hmac
import os
import socket
import sys
import warnings
from inspect import Traceback
from multiprocessing import ProcessError
from os import chmod, urandom
from subprocess import PIPE, Popen
from tempfile import mktemp
from types import MappingProxyType
from typing import (
    Any, Callable, Coroutine, Dict, Mapping, Optional, Set, Tuple, Type,
)

from aiomisc.counters import Statistic
from aiomisc.thread_pool import threaded
from aiomisc.utils import (
    bind_socket, cancel_tasks, fast_uuid4, set_exception, shield,
)
from aiomisc_log import LOG_FORMAT, LOG_LEVEL
from aiomisc_worker import (
    COOKIE_SIZE, INET_AF, INT_SIGNAL, SIGNAL, AddressType, PacketTypes, T, log,
)
from aiomisc_worker.protocol import AsyncProtocol, FileIOProtocol


if sys.version_info < (3, 7):
    warnings.warn(
        "Python 3.6 works not well see https://bugs.python.org/issue37380",
        RuntimeWarning,
    )


class WorkerPoolStatistic(Statistic):
    processes: int
    spawning: int
    queue_size: int
    submitted: int
    sum_time: float
    done: int
    success: int
    error: int
    bad_auth: int
    task_added: int


class WorkerPool:
    tasks: asyncio.Queue
    server: asyncio.AbstractServer
    address: AddressType
    initializer: Optional[Callable[[], Any]]
    initializer_args: Tuple[Any, ...]
    initializer_kwargs: Mapping[str, Any]

    _supervisor: Popen
    worker_ids: Tuple[bytes, ...]
    pids: Set[int]

    if hasattr(socket, "AF_UNIX"):
        def _create_socket(self) -> None:
            path = mktemp(suffix=".sock", prefix="worker-")
            self.socket = bind_socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM,
                address=path,
            )
            self.address = path
            chmod(path, 0o600)
    else:
        def _create_socket(self) -> None:
            self.socket = bind_socket(
                INET_AF,
                socket.SOCK_STREAM,
                address="localhost",
                reuse_addr=False,
                reuse_port=False,
            )
            self.address = self.socket.getsockname()[:2]

    @staticmethod
    def _kill_process(process: Popen) -> None:
        if process.returncode is not None:
            return None
        log.debug("Terminating worker pool process PID: %s", process.pid)
        process.kill()

    @threaded
    def __create_supervisor(self, *identity: str) -> Popen:
        if self.__closing:
            raise RuntimeError("Pool closed")

        env = dict(os.environ)
        env["AIOMISC_NO_PLUGINS"] = ""
        process = Popen(
            [sys.executable, "-m", "aiomisc_worker"], stdin=PIPE, env=env,
        )

        assert process.stdin

        log_level = (
            log.getEffectiveLevel()
            if LOG_LEVEL is None
            else LOG_LEVEL.get()
        )

        log_format = "color" if LOG_FORMAT is None else LOG_FORMAT.get()

        proto_stdin = FileIOProtocol(process.stdin)

        proto_stdin.send((log_level, log_format))
        proto_stdin.send(self.address)
        proto_stdin.send(self.__cookie)
        proto_stdin.send(identity)
        proto_stdin.send((
            self.initializer,
            self.initializer_args,
            dict(self.initializer_kwargs),
        ))
        process.stdin.close()
        return process

    def __init__(
        self, workers: int, max_overflow: int = 0, *,
        initializer: Optional[Callable[[], Any]] = None,
        initializer_args: Tuple[Any, ...] = (),
        initializer_kwargs: Mapping[str, Any] = MappingProxyType({}),
        statistic_name: Optional[str] = None,
    ):
        self._create_socket()
        self.__cookie = urandom(COOKIE_SIZE)
        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self.__futures: Set[asyncio.Future] = set()
        self.__task_store: Set[asyncio.Task] = set()
        self.__closing = False
        self.__closing_lock = asyncio.Lock()
        self._statistic = WorkerPoolStatistic(name=statistic_name)
        self.__max_overflow = max_overflow
        self.workers = workers
        self.pids = set()
        self.initializer = initializer
        self.initializer_args = initializer_args
        self.initializer_kwargs = initializer_kwargs

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self.__loop is None:
            self.__loop = asyncio.get_running_loop()
        return self.__loop

    async def __handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        proto = AsyncProtocol(reader, writer)
        packet_type, worker_id, digest, pid = await proto.receive()

        async with self.__closing_lock:
            if self.__closing:
                proto.close()

        if packet_type == PacketTypes.BAD_INITIALIZER:
            packet_type, exc = await proto.receive()
            if packet_type != PacketTypes.EXCEPTION:
                await proto.send(PacketTypes.BAD_PACKET)
            else:
                set_exception(self.__futures, exc)
            await self.close()
            return

        if packet_type != PacketTypes.AUTH:
            await proto.send(PacketTypes.BAD_PACKET)
            if writer.can_write_eof():
                writer.write_eof()
            return

        if worker_id not in self.worker_ids:
            log.error("Unknown worker with id %r", worker_id)
            return

        expected_digest = hmac.HMAC(
            self.__cookie,
            worker_id,
            digestmod=hashlib.sha256,
        ).digest()

        if expected_digest != digest:
            await proto.send(PacketTypes.AUTH_FAIL)
            if writer.can_write_eof():
                writer.write_eof()
            log.debug("Bad digest %r expected %r", digest, expected_digest)
            return

        await proto.send(PacketTypes.AUTH_OK)
        self._statistic.processes += 1
        self._statistic.spawning += 1
        self.pids.add(pid)

        try:
            while not reader.at_eof():
                func: Callable
                args: Tuple[Any, ...]
                kwargs: Dict[str, Any]
                result_future: asyncio.Future
                process_future: asyncio.Future

                (
                    func, args, kwargs, result_future, process_future,
                ) = await self.tasks.get()

                if process_future.done() or result_future.done():
                    continue

                try:
                    process_future.set_result(pid)
                    await proto.send((PacketTypes.REQUEST, func, args, kwargs))
                    packet_type, payload = await proto.receive()

                    if result_future.done():
                        log.debug(
                            "Result future %r already done, skipping",
                            result_future,
                        )
                        continue

                    if packet_type == PacketTypes.RESULT:
                        result_future.set_result(payload)
                    elif packet_type in (
                        PacketTypes.EXCEPTION, PacketTypes.CANCELLED,
                    ):
                        result_future.set_exception(payload)
                    del packet_type, payload
                except (asyncio.IncompleteReadError, ConnectionError):
                    if not result_future.done():
                        result_future.set_exception(
                            ProcessError(f"Process {pid!r} unexpected exited"),
                        )
                    break
                except Exception as e:
                    if not result_future.done():
                        result_future.set_exception(e)

                    if not writer.is_closing():
                        if writer.can_write_eof():
                            writer.write_eof()
                        writer.close()
                    raise
        finally:
            self._statistic.processes -= 1
            self.pids.remove(pid)

    def __start_handler(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> asyncio.Task:
        return self.__task(self.__handle_client(reader, writer))

    def __task_add(self, task: asyncio.Task) -> None:
        self._statistic.task_added += 1
        task.add_done_callback(self.__task_store.remove)
        self.__task_store.add(task)

    def __task(self, coroutine: Coroutine) -> asyncio.Task:
        task = self.loop.create_task(coroutine)
        self.__task_add(task)
        return task

    async def start(self) -> None:
        self.tasks = asyncio.Queue(maxsize=self.__max_overflow)
        self.server = await asyncio.start_server(
            self.__start_handler,
            sock=self.socket,
        )
        del self.socket

        self.worker_ids = tuple(
            fast_uuid4().bytes for _ in range(self.workers)
        )
        self._supervisor = await self.__create_supervisor(*self.worker_ids)

    def __create_future(self) -> asyncio.Future:
        future = self.loop.create_future()
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        return future

    def __reject_futures(self) -> None:
        set_exception(self.__futures, RuntimeError("Pool closed"))

    @shield
    async def close(self) -> None:
        async with self.__closing_lock:
            if self.__closing:
                return

            self._kill_supervisor()
            self.__closing = True
            self.server.close()
            await self.server.wait_closed()

            await cancel_tasks(tuple(self.__task_store))
            await cancel_tasks(tuple(self.__futures))

    def _kill_supervisor(self) -> None:
        supervisor: Optional[Popen] = getattr(self, "_supervisor", None)
        if supervisor is None or supervisor.poll() is not None:
            return

        log.debug(
            "Sending %r to supervisor process PID: %d. Workers: %r",
            INT_SIGNAL, supervisor.pid, self.pids,
        )
        os.kill(self._supervisor.pid, INT_SIGNAL)

    def __del__(self) -> None:
        self._kill_supervisor()

    async def create_task(
        self, func: Callable[..., T],
        *args: Any, **kwargs: Any
    ) -> T:
        result_future = self.__create_future()
        process_future = self.__create_future()

        await self.tasks.put((
            func, args, kwargs, result_future, process_future,
        ))

        pid: int = await process_future

        try:
            return await result_future
        except asyncio.CancelledError:
            log.debug("Sending %r to worker PID: %d", SIGNAL, pid)
            os.kill(pid, SIGNAL)
            raise

    async def __aenter__(self) -> "WorkerPool":
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: Type[Exception],
        exc_val: Exception, exc_tb: Traceback,
    ) -> None:
        await self.close()
