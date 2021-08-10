import asyncio
import os
import pickle
import socket
import sys
import uuid
import warnings
from inspect import Traceback
from itertools import chain
from multiprocessing import AuthenticationError, ProcessError
from os import chmod, urandom
from subprocess import PIPE, Popen
from tempfile import mktemp
from types import MappingProxyType
from typing import (
    Any, Callable, Coroutine, Dict, Mapping, Optional, Set, Tuple, Type,
)

from aiomisc.counters import Statistic
from aiomisc.log.config import LOG_FORMAT, LOG_LEVEL
from aiomisc.thread_pool import threaded
from aiomisc.utils import bind_socket, cancel_tasks
from aiomisc.worker_pool.constants import (
    COOKIE_SIZE, HASHER, INET_AF, SIGNAL, AddressType, Header, PacketTypes, T,
    log,
)


if sys.version_info < (3, 7):
    warnings.warn(
        "Python 3.6 works not well see https://bugs.python.org/issue37380",
        RuntimeWarning,
    )


class WorkerPoolStatistic(Statistic):
    processes: int
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

    if hasattr(socket, "AF_UNIX"):
        def _create_socket(self) -> None:
            path = mktemp(suffix=".sock", prefix="worker-")
            self.socket = bind_socket(
                socket.AF_UNIX,
                socket.SOCK_STREAM,
                address=path, port=0,
            )
            self.address = path
            chmod(path, 0o600)
    else:
        def _create_socket(self) -> None:
            self.socket = bind_socket(
                INET_AF,
                socket.SOCK_STREAM,
                address="localhost",
                port=0,
            )
            self.address = self.socket.getsockname()[:2]

    @staticmethod
    def _kill_process(process: Popen) -> None:
        if process.returncode is not None:
            return None
        log.debug("Terminating worker pool process PID: %s", process.pid)
        process.kill()

    @threaded
    def __create_process(self, identity: str) -> Popen:
        if self.__closing:
            raise RuntimeError("Pool closed")

        process = Popen(
            [sys.executable, "-m", "aiomisc.worker_pool.process"],
            stdin=PIPE, env=os.environ,
        )
        self.__spawning[identity] = process
        log.debug("Spawning new worker pool process PID: %s", process.pid)

        assert process.stdin

        log_level = (
            log.getEffectiveLevel() if LOG_LEVEL is None else LOG_LEVEL.get()
        )
        log_format = "color" if LOG_FORMAT is None else LOG_FORMAT.get().value

        process.stdin.write(
            pickle.dumps((
                self.address, self.__cookie, identity,
                log_level, log_format,
            )),
        )
        process.stdin.close()

        return process

    def __init__(
        self, workers: int, max_overflow: int = 0, *,
        process_poll_time: float = 0.1,
        initializer: Optional[Callable[[], Any]] = None,
        initializer_args: Tuple[Any, ...] = (),
        initializer_kwargs: Mapping[str, Any] = MappingProxyType({}),
    ):
        self._create_socket()
        self.__cookie = urandom(COOKIE_SIZE)
        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self.__futures: Set[asyncio.Future] = set()
        self.__spawning: Dict[str, Popen] = dict()
        self.__task_store: Set[asyncio.Task] = set()
        self.__closing = False
        self.__starting: Dict[str, asyncio.Future] = dict()
        self._statistic = WorkerPoolStatistic()
        self.processes: Set[Popen] = set()
        self.workers = workers
        self.tasks = asyncio.Queue(maxsize=max_overflow)
        self.process_poll_time = process_poll_time
        self.initializer = initializer
        self.initializer_args = initializer_args
        self.initializer_kwargs = initializer_kwargs

    async def __wait_process(self, process: Popen) -> None:
        while process.poll() is None:
            await asyncio.sleep(self.process_poll_time)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self.__loop is None:
            self.__loop = asyncio.get_event_loop()
        return self.__loop

    @staticmethod
    async def __wait_closed(writer: asyncio.StreamWriter) -> None:
        if writer.is_closing():
            return

        writer.close()

        if hasattr(writer, "wait_closed"):
            await writer.wait_closed()

    async def __handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> None:
        async def receive() -> Tuple[PacketTypes, Any]:
            header = await reader.readexactly(Header.size)
            packet_type, payload_length = Header.unpack(header)
            payload = await reader.readexactly(payload_length)
            data = pickle.loads(payload)
            return PacketTypes(packet_type), data

        async def send(packet_type: PacketTypes, data: Any) -> None:
            payload = pickle.dumps(data)
            header = Header.pack(packet_type.value, len(payload))
            writer.write(header)
            writer.write(payload)

        async def step(
            func: Callable, args: Tuple[Any, ...],
            kwargs: Dict[str, Any], result_future: asyncio.Future,
        ) -> None:
            await send(PacketTypes.REQUEST, (func, args, kwargs))
            self._statistic.submitted += 1

            packet_type, result = await receive()
            self._statistic.done += 1

            if packet_type == PacketTypes.RESULT:
                result_future.set_result(result)
                self._statistic.success += 1
                return None

            if packet_type == PacketTypes.EXCEPTION:
                result_future.set_exception(result)
                self._statistic.error += 1
                return None

            if packet_type == PacketTypes.CANCELLED:
                if not result_future.done():
                    result_future.set_exception(asyncio.CancelledError)
                return None

            raise ValueError("Unknown packet type")

        async def handler(start_event: asyncio.Event) -> None:
            log.debug("Starting to handle client")

            packet_type, salt = await receive()
            assert packet_type == PacketTypes.AUTH_SALT

            packet_type, digest = await receive()
            assert packet_type == PacketTypes.AUTH_DIGEST

            hasher = HASHER()
            hasher.update(salt)
            hasher.update(self.__cookie)

            if digest != hasher.digest():
                exc = AuthenticationError("Invalid cookie")
                self._statistic.bad_auth += 1
                await send(PacketTypes.EXCEPTION, exc)
                raise exc

            await send(PacketTypes.AUTH_OK, True)

            log.debug("Client authorized")

            packet_type, identity = await receive()
            assert packet_type == PacketTypes.IDENTITY
            process = self.__spawning.pop(identity)
            starting: asyncio.Future = self.__starting.pop(identity)

            if self.initializer is not None:
                initializer_done = self.__create_future()

                await step(
                    self.initializer,
                    self.initializer_args,
                    dict(self.initializer_kwargs),
                    initializer_done,
                )

                try:
                    await initializer_done
                except Exception as e:
                    starting.set_exception(e)
                    raise
                else:
                    starting.set_result(None)
                finally:
                    start_event.set()
            else:
                starting.set_result(None)
                start_event.set()

            try:
                while True:
                    func: Callable
                    args: Tuple[Any, ...]
                    kwargs: Dict[str, Any]
                    result_future: asyncio.Future
                    process_future: asyncio.Future

                    self._statistic.processes += 1
                    (
                        func, args, kwargs, result_future, process_future,
                    ) = await self.tasks.get()

                    try:
                        if process_future.done():
                            continue

                        process_future.set_result(process)

                        if result_future.done():
                            continue

                        await step(func, args, kwargs, result_future)
                    except asyncio.IncompleteReadError:
                        await self.__wait_process(process)
                        self.__on_exit(process)

                        result_future.set_exception(
                            ProcessError(
                                "Process {!r} exited with code {!r}".format(
                                    process, process.returncode,
                                ),
                            ),
                        )
                        break
                    except Exception as e:
                        if not result_future.done():
                            self.loop.call_soon(result_future.set_exception, e)

                        if not writer.is_closing():
                            self.loop.call_soon(writer.close)

                        await self.__wait_process(process)
                        self.__on_exit(process)

                        raise
                    finally:
                        self._statistic.processes -= 1
            finally:
                await self.__wait_closed(writer)

        start_event = asyncio.Event()
        task = self.loop.create_task(handler(start_event))
        await start_event.wait()
        self.__task_add(task)

        await task

    def __task_add(self, task: asyncio.Task) -> None:
        self._statistic.task_added += 1
        task.add_done_callback(self.__task_store.remove)
        self.__task_store.add(task)

    def __task(self, coroutine: Coroutine) -> asyncio.Task:
        task = self.loop.create_task(coroutine)
        self.__task_add(task)
        return task

    async def start(self) -> None:
        self.server = await asyncio.start_server(
            self.__handle_client,
            sock=self.socket,
        )

        tasks = []

        for n in range(self.workers):
            log.debug("Starting worker %d", n)
            tasks.append(self.__spawn_process())

        await asyncio.gather(*tasks)

    def __on_exit(self, process: Popen) -> None:
        async def respawn() -> None:
            if self.__closing:
                return None

            await self.__spawn_process()
            self.processes.remove(process)

        self.__task(respawn())

    async def __spawn_process(self) -> None:
        log.debug("Spawning new process")

        identity = uuid.uuid4().hex
        start_future = self.__create_future()
        self.__starting[identity] = start_future
        process = await self.__create_process(identity)
        await start_future
        self.processes.add(process)

    def __create_future(self) -> asyncio.Future:
        future = self.loop.create_future()
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        return future

    def __reject_futures(self) -> None:
        for future in self.__futures:
            if future.done():
                continue
            future.set_exception(RuntimeError("Pool closed"))

    async def close(self) -> None:
        if self.__closing:
            return

        self.__closing = True

        await cancel_tasks(
            chain(tuple(self.__task_store), tuple(self.__futures)),
        )

        while self.processes:
            self._kill_process(self.processes.pop())

    async def create_task(
        self, func: Callable[..., T],
        *args: Any, **kwargs: Any
    ) -> T:
        result_future = self.__create_future()
        process_future = self.__create_future()

        await self.tasks.put((
            func, args, kwargs, result_future, process_future,
        ))

        process: Popen = await process_future

        try:
            return await result_future
        except asyncio.CancelledError:
            os.kill(process.pid, SIGNAL)
            raise

    async def __aenter__(self) -> "WorkerPool":
        await self.start()
        return self

    async def __aexit__(
        self, exc_type: Type[Exception],
        exc_val: Exception, exc_tb: Traceback,
    ) -> None:
        await self.close()
