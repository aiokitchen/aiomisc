import asyncio
import hashlib
import logging
import pickle
import socket
import uuid
from enum import IntEnum
from inspect import Traceback
from multiprocessing import AuthenticationError, Process, ProcessError
from os import chmod, urandom
from struct import Struct
from tempfile import mktemp
from typing import (
    Any, Callable, Dict, Optional, Set, Tuple, Type, TypeVar, Union,
)

from aiomisc.utils import bind_socket


T = TypeVar("T")
AddressType = Union[str, Tuple[str, int]]

log = logging.getLogger(__name__)
Header = Struct("!BI")

SALT_SIZE = 64
COOKIE_SIZE = 128
HASHER = hashlib.sha256


class PacketTypes(IntEnum):
    REQUEST = 0
    EXCEPTION = 1
    RESULT = 2
    AUTH_SALT = 50
    AUTH_DIGEST = 51
    AUTH_OK = 59
    IDENTITY = 60


INET_AF = socket.AF_INET6


def _inner(address: AddressType, cookie: bytes, identity: str) -> None:
    family = (
        socket.AF_UNIX if isinstance(address, str) else INET_AF
    )

    with socket.socket(family, socket.SOCK_STREAM) as sock:
        log.debug("Connecting...")
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
                return True

            if packet_type == packet_type.REQUEST:
                response_type = PacketTypes.RESULT
                try:
                    result = func(*args, **kwargs)
                except Exception as e:
                    response_type = PacketTypes.EXCEPTION
                    result = e
                    logging.exception("Exception when processing request")

                send(response_type, result)
            return False

        log.debug("Starting authorization")
        auth(cookie)
        del cookie

        send(PacketTypes.IDENTITY, identity)
        log.debug("Worker ready")
        try:
            while not step():
                pass
        except KeyboardInterrupt:
            return


class WorkerPool:
    tasks: asyncio.Queue
    server: asyncio.AbstractServer
    address: AddressType

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

    if hasattr(Process, "kill"):
        @staticmethod
        def _kill_process(process: Process) -> None:
            process.kill()
    else:
        @staticmethod
        def _kill_process(process: Process) -> None:
            process.terminate()

    def __create_process(self, identity: str) -> Process:
        process = Process(
            target=_inner,
            args=(self.address, self.__cookie, identity),
        )
        self.loop.call_soon(process.start)
        return process

    def __init__(
        self, workers: int, max_overflow: int = 0,
        process_poll_time: float = 0.1
    ):
        self._create_socket()
        self.__cookie = urandom(COOKIE_SIZE)
        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self.__futures: Set[asyncio.Future] = set()
        self.__spawning: Dict[str, Process] = dict()
        self.__task_store: Set[asyncio.Task] = set()
        self.processes: Set[Process] = set()
        self.workers = workers
        self.tasks = asyncio.Queue(maxsize=max_overflow)
        self.process_poll_time = process_poll_time

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self.__loop is None:
            self.__loop = asyncio.get_event_loop()
        return self.__loop

    async def __handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
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
            await writer.drain()

        async def step(
            func: Callable, args: Tuple[Any, ...],
            kwargs: Dict[str, Any], result_future: asyncio.Future
        ) -> None:
            await send(PacketTypes.REQUEST, (func, args, kwargs))

            packet_type, result = await receive()

            if packet_type == PacketTypes.RESULT:
                result_future.set_result(result)
                return None

            if packet_type == PacketTypes.EXCEPTION:
                result_future.set_exception(result)
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
                exc = AuthenticationError("Invalid cookie")
                await send(PacketTypes.EXCEPTION, exc)
                raise exc

            await send(PacketTypes.AUTH_OK, True)

            log.debug("Client authorized")

            packet_type, identity = await receive()
            assert packet_type == PacketTypes.IDENTITY

            process = self.__spawning.pop(identity)

            while True:
                func: Callable
                args: Tuple[Any, ...]
                kwargs: Dict[str, Any]
                result_future: asyncio.Future
                process_future: asyncio.Future

                (
                    func, args, kwargs, result_future, process_future,
                ) = await self.tasks.get()

                process_future.set_result(process)

                try:
                    if result_future.done():
                        continue

                    await step(func, args, kwargs, result_future)
                except asyncio.IncompleteReadError:
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
                        result_future.set_exception(e)

                    if not writer.is_closing():
                        self.loop.call_soon(writer.close)

                    raise

        task = self.loop.create_task(handler())
        task.add_done_callback(self.__task_store.remove)
        self.__task_store.add(task)
        await task

    async def start_server(self) -> None:
        self.server = await asyncio.start_server(
            self.__handle_client,
            sock=self.socket,
        )

        for n in range(self.workers):
            log.debug("Starting worker %d", n)
            self.__spawn_process()

        self.__task_store.add(self.loop.create_task(self.supervise()))

    def __spawn_process(self) -> None:
        log.debug("Spawning new process")
        identity = uuid.uuid4().hex
        process = self.__create_process(identity)
        self.processes.add(process)
        self.__spawning[identity] = process

    async def supervise(self) -> None:
        while True:
            for process in tuple(self.processes):
                if process.is_alive():
                    continue

                log.debug(
                    "Process %r[%d] dead with exitcode %r, respawning",
                    process, process.pid, process.exitcode,
                )
                self.processes.remove(process)
                self.loop.call_soon(self.__spawn_process)
            await asyncio.sleep(self.process_poll_time)

    def __create_future(self) -> asyncio.Future:
        future = self.loop.create_future()
        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        return future

    async def __cancel_tasks(self) -> None:
        tasks = set()

        for task in tuple(self.__task_store):
            if task.done():
                continue
            task.cancel()
            tasks.add(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        self.__task_store.clear()

    async def __reject_futures(self) -> None:
        while self.__futures:
            future = self.__futures.pop()
            if future.done():
                continue

            future.set_exception(RuntimeError("Pool closed"))
            await asyncio.sleep(0)

    async def close(self) -> None:
        await asyncio.gather(
            self.__cancel_tasks(),
            self.__reject_futures(),
            return_exceptions=True,
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

        process: Process = await process_future

        try:
            return await result_future
        except asyncio.CancelledError:
            self._kill_process(process)
            raise

    async def __aenter__(self) -> "WorkerPool":
        await self.start_server()
        return self

    async def __aexit__(
        self, exc_type: Type[Exception],
        exc_val: Exception, exc_tb: Traceback
    ) -> None:
        await self.close()
