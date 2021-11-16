import asyncio
import os
import pickle
import socket
import sys
import warnings
from inspect import Traceback
from multiprocessing import AuthenticationError, ProcessError
from os import chmod, urandom
from subprocess import PIPE, Popen
from tempfile import mktemp
from types import MappingProxyType
from typing import (
    Any, Awaitable, Callable, Coroutine, Dict, Mapping, Optional, Set, Tuple,
    Type,
)

from aiomisc.counters import Statistic
from aiomisc.thread_pool import threaded
from aiomisc.utils import bind_socket, cancel_tasks, fast_uuid4, shield
from aiomisc_log import LOG_FORMAT, LOG_LEVEL
from aiomisc_worker import (
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
    def _kill_process(process: Popen) -> None:
        if process.returncode is not None:
            return None
        log.debug("Terminating worker pool process PID: %s", process.pid)
        process.kill()

    @threaded
    def __create_process(self, identity: str) -> Popen:
        if self.__closing:
            raise RuntimeError("Pool closed")

        env = dict(os.environ)
        env["AIOMISC_NO_PLUGINS"] = ""
        process = Popen(
            [sys.executable, "-m", "aiomisc_worker"],
            stdin=PIPE, env=env,
        )
        self.__spawning[identity] = process
        self.processes.add(process)

        log.debug("Spawning new worker pool process PID: %s", process.pid)

        assert process.stdin

        log_level = (
            log.getEffectiveLevel() if LOG_LEVEL is None else LOG_LEVEL.get()
        )
        log_format = "color" if LOG_FORMAT is None else LOG_FORMAT.get()

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
        self.__closing_lock = asyncio.Lock()
        self.__starting: Dict[str, asyncio.Future] = dict()
        self._statistic = WorkerPoolStatistic()
        self.processes: Set[Popen] = set()
        self.workers = workers
        self.tasks = asyncio.Queue(maxsize=max_overflow)
        self.process_poll_time = process_poll_time
        self.initializer = initializer
        self.initializer_args = initializer_args
        self.initializer_kwargs = initializer_kwargs

    async def __check_is_closed(self) -> bool:
        async with self.__closing_lock:
            return self.__closing

    async def __wait_process(self, process: Popen) -> None:
        await self.loop.run_in_executor(None, process.kill)

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
                log.debug(
                    "Sending initializer %r to the process PID: %d",
                    self.initializer, process.pid,
                )
                initializer_done = self.__create_future()

                await step(
                    self.initializer,
                    self.initializer_args,
                    dict(self.initializer_kwargs),
                    initializer_done,
                )

                try:
                    await initializer_done
                    log.debug("Initializer done")
                except Exception as e:
                    log.debug("Initializer fails")
                    if not starting.done():
                        starting.set_exception(e)
                    raise
                else:
                    if not starting.done():
                        starting.set_result(None)
                finally:
                    start_event.set()
            else:
                if not starting.done():
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
                    except (asyncio.IncompleteReadError, ConnectionError):
                        await self.__wait_process(process)
                        await self.__on_exit(process)

                        if not result_future.done():
                            result_future.set_exception(
                                ProcessError(
                                    f"Process {process!r} exited with "
                                    f"code {process.returncode!r}",
                                ),
                            )
                        break
                    except Exception as e:
                        if not result_future.done():
                            self.loop.call_soon(result_future.set_exception, e)

                        if not writer.is_closing():
                            self.loop.call_soon(writer.close)

                        await self.__wait_process(process)
                        await self.__on_exit(process)

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

    async def __on_exit(self, process: Popen) -> None:
        self.processes.remove(process)

        if await self.__check_is_closed():
            return None

        await self.__spawn_process()

    def __spawn_process(self) -> Awaitable[None]:
        log.debug("Spawning new process")

        identity = fast_uuid4().hex
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
        @threaded
        def killer() -> None:
            while self.processes:
                self._kill_process(self.processes.pop())

        async with self.__closing_lock:
            if self.__closing:
                return

            self.__closing = True

            await cancel_tasks(tuple(self.__task_store))
            await killer()
            await cancel_tasks(tuple(self.__futures))

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
