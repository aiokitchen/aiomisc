import asyncio
import os
import pickle
import socket
import sys
import warnings
from inspect import Traceback
from multiprocessing import AuthenticationError, Process, ProcessError
from os import chmod, urandom
from random import getrandbits
from tempfile import mktemp
from types import MappingProxyType
from typing import (
    Any, Callable, Coroutine, Dict, Mapping, Optional, Set, Tuple, Type,
)

from aiomisc.counters import Statistic
from aiomisc.thread_pool import threaded
from aiomisc.utils import bind_socket, cancel_tasks, shield
from aiomisc_log import LOG_FORMAT, LOG_LEVEL
from aiomisc_worker import (
    COOKIE_SIZE, HASHER, INET_AF, SIGNAL, AddressType, Header, PacketTypes, T,
    log, worker_process,
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
            )
            self.address = self.socket.getsockname()[:2]

    @staticmethod
    def _kill_process(process: Process) -> None:
        if not process.is_alive():
            return None
        log.debug("Terminating worker pool process PID: %s", process.pid)
        process.kill()

    @threaded
    def __create_process(self, identity: int) -> Process:
        if self.__closing:
            raise RuntimeError("Pool closed")

        log_level = (
            log.getEffectiveLevel() if LOG_LEVEL is None else LOG_LEVEL.get()
        )
        log_format = "color" if LOG_FORMAT is None else LOG_FORMAT.get().value

        process = Process(
            target=worker_process.process,
            args=(
                self.address,
                self.__cookie,
                identity,
                log_level,
                log_format,
            ),
        )

        self.__spawning[identity] = process
        self.processes.add(process)

        process.start()

        log.debug("Started worker pool process PID: %s", process.pid)

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
        self.__spawning: Dict[int, Process] = dict()
        self.__task_store: Set[asyncio.Task] = set()
        self.__closing = False
        self.__closing_lock = asyncio.Lock()
        self.__starting: Dict[int, asyncio.Future] = dict()
        self._statistic = WorkerPoolStatistic()
        self.processes: Set[Process] = set()
        self.workers = workers
        self.tasks = asyncio.Queue(maxsize=max_overflow)
        self.process_poll_time = process_poll_time
        self.initializer = initializer
        self.initializer_args = initializer_args
        self.initializer_kwargs = initializer_kwargs

    async def __wait_process_exit(self, process: Process) -> None:
        await self.loop.run_in_executor(None, self._kill_process, process)
        while process.is_alive():
            await asyncio.sleep(self.process_poll_time)

    async def __check_closed(self) -> bool:
        async with self.__closing_lock:
            return self.__closing

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

    def __handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
    ) -> asyncio.Task:
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

        async def handler() -> None:
            log.debug("Starting to handle client")

            packet_type, salt = await receive()
            assert packet_type == PacketTypes.AUTH_SALT

            packet_type, digest = await receive()
            assert packet_type == PacketTypes.AUTH_DIGEST

            hasher = HASHER()
            hasher.update(salt)
            hasher.update(self.__cookie)

            if digest != hasher.digest():
                exc: Exception = AuthenticationError("Invalid cookie")
                self._statistic.bad_auth += 1
                await send(PacketTypes.EXCEPTION, exc)
                raise exc

            await send(PacketTypes.AUTH_OK, True)

            log.debug("Client authorized")

            packet_type, identity = await receive()
            assert packet_type == PacketTypes.IDENTITY
            process = self.__spawning.pop(identity)
            starting: asyncio.Future = self.__starting.pop(identity)

            if starting.done():
                # Starting future
                await self.__wait_process_exit(process)
                return await starting

            if self.initializer is not None:
                initializer_done = self.__create_future()

                log.debug("Awaiting initializer %r", self.initializer)
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
                    self._kill_process(process)
                    raise
                else:
                    starting.set_result(None)
            else:
                # if not starting.done():
                starting.set_result(None)

            try:
                log.debug("Waiting tasks")
                while not self.__closing:
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
                        if process_future.done() or result_future.done():
                            continue
                        process_future.set_result(process)
                        await step(func, args, kwargs, result_future)
                    except asyncio.IncompleteReadError:
                        self._kill_process(process)
                        await self.__wait_process_exit(process)
                        await self.__on_exit(process)

                        if not result_future.done():
                            result_future.set_exception(
                                ProcessError(
                                    "Process {!r} exited with code {!r}".format(
                                        process, process.exitcode,
                                    ),
                                ),
                            )
                        break
                    except Exception as e:
                        if not result_future.done():
                            self.loop.call_soon(result_future.set_exception, e)

                        if not writer.is_closing():
                            self.loop.call_soon(writer.close)

                        await self.__wait_process_exit(process)
                        await self.__on_exit(process)

                        raise
                    finally:
                        self._statistic.processes -= 1
            finally:
                await self.__wait_closed(writer)
                log.debug("Handler done")

        task = self.loop.create_task(handler())
        self.__task_add(task)
        return task

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

    async def __on_exit(self, process: Process) -> None:
        self.processes.remove(process)

        log.debug(
            "Process %r exit with code %r, respawning",
            process.pid, process.exitcode,
        )

        await self.__spawn_process()

    def __spawn_process(self) -> asyncio.Future:
        log.debug("Spawning new process, active %d", len(self.processes))
        identity = getrandbits(128)
        start_future = self.__create_future()
        self.__starting[identity] = start_future
        self.__create_process(identity)
        return start_future

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

    @shield
    async def close(self) -> None:
        log.debug("Closing worker pool %r", self)

        if await self.__check_closed():
            return

        @threaded
        def killer() -> None:
            while self.processes:
                self._kill_process(self.processes.pop())

        async with self.__closing_lock:
            self.__closing = True

            await cancel_tasks(self.__task_store)
            await killer()
            await cancel_tasks(self.__futures)

    async def create_task(
        self, func: Callable[..., T],
        *args: Any, **kwargs: Any
    ) -> T:
        result_future = self.__create_future()
        process_future = self.__create_future()

        await self.tasks.put((
            func, args, kwargs, result_future, process_future,
        ))

        process: Process = await process_future

        try:
            return await result_future
        except asyncio.CancelledError:
            if process.pid is not None:
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
