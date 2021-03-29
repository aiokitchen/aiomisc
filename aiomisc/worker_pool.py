import asyncio
import hashlib
import logging
import pickle
import socket
from enum import IntEnum
from inspect import Traceback
from multiprocessing import Process, ProcessError, AuthenticationError
from os import chmod, urandom
from struct import Struct
from tempfile import mktemp
from typing import Tuple, Set, Callable, Any, Dict, Optional, Union, TypeVar, \
    Type

from aiomisc.utils import bind_socket


T = TypeVar("T")
AddressType = Union[str, Tuple[str, int]]

log = logging.getLogger(__name__)
Header = Struct("!BI")
SALT_SIZE = 64
COOKIE_SIZE = 128
HASHER = hashlib.sha256
HASH_SIZE = len(HASHER(b'').digest())


class PacketTypes(IntEnum):
    REQUEST = 0
    EXCEPTION = 1
    RESULT = 2


INET_AF = socket.AF_INET6


def _inner(address: AddressType, cookie: bytes) -> None:
    def step() -> Optional[bool]:
        header = sock.recv(Header.size)

        if not header:
            return True

        packet_type, payload_length = Header.unpack(header)
        payload = sock.recv(payload_length)

        func, args, kwargs = pickle.loads(payload)

        response_type = PacketTypes.RESULT
        try:
            result = func(*args, **kwargs)
        except Exception as e:
            response_type = PacketTypes.EXCEPTION
            result = e
            logging.exception("Exception when processing request")

        payload = pickle.dumps(result)
        header = Header.pack(response_type.value, len(payload))
        sock.send(header)
        sock.send(payload)
        return None

    family = (
        socket.AF_UNIX if isinstance(address, str) else INET_AF
    )

    with socket.socket(family, socket.SOCK_STREAM) as sock:
        log.debug("Connecting...")
        sock.connect(address)

        log.debug("Starting authorization")
        hasher = HASHER()
        salt = urandom(SALT_SIZE)
        sock.send(salt)

        hasher.update(salt)
        hasher.update(cookie)
        sock.send(hasher.digest())

        del cookie
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
                address=path, port=0
            )
            self.address = path
            chmod(path, 0o600)
    else:
        def _create_socket(self) -> None:
            self.socket = bind_socket(
                INET_AF,
                socket.SOCK_STREAM,
                address='localhost',
                port=0
            )
            self.address = self.socket.getsockname()[:2]

    def _create_process(self) -> Process:
        process = Process(target=_inner, args=(self.address, self.__cookie))
        process.start()
        return process

    def __init__(self, workers: int, max_overflow: int = 0):
        self.__cookie = urandom(COOKIE_SIZE)
        self.__loop: Optional[asyncio.AbstractEventLoop] = None
        self._create_socket()
        self.tasks = asyncio.Queue(maxsize=max_overflow)
        self.workers = workers
        self._futures: Set[asyncio.Future] = set()
        self.processes: Set[Process] = set()
        self.task_store: Set[asyncio.Task] = set()
        self._create_process_lock = asyncio.Lock()
        self._current_process: Optional[Process] = None
        self._current_process_event: Optional[asyncio.Event] = None

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self.__loop is None:
            self.__loop = asyncio.get_event_loop()
        return self.__loop

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if (
            self._current_process is None or
            self._current_process_event is None
        ):
            raise RuntimeError("No process found")

        process = self._current_process

        async def step(
            func: Callable, args: Tuple[Any, ...],
            kwargs: Dict[str, Any], result_future: asyncio.Future
        ) -> None:
            payload = pickle.dumps((func, args, kwargs))
            header = Header.pack(PacketTypes.REQUEST.value, len(payload))
            writer.write(header)
            writer.write(payload)
            await writer.drain()

            header = await reader.readexactly(Header.size)
            packet_type, payload_length = Header.unpack(header)
            payload = await reader.readexactly(payload_length)

            if packet_type == PacketTypes.RESULT:
                result_future.set_result(pickle.loads(payload))
                return None

            if packet_type == PacketTypes.EXCEPTION:
                result_future.set_exception(pickle.loads(payload))
                return None

            raise ValueError("Unknown packet type")

        async def handler() -> None:
            log.debug("Starting to handle client")
            salt = await reader.readexactly(SALT_SIZE)
            digest = await reader.readexactly(HASH_SIZE)

            hasher = HASHER()
            hasher.update(salt)
            hasher.update(self.__cookie)

            if digest != hasher.digest():
                raise AuthenticationError("Invalid cookie")
            log.debug("Client authorized")

            while True:
                func: Callable
                args: Tuple[Any, ...]
                kwargs: Dict[str, Any]
                result_future: asyncio.Future
                process_future: asyncio.Future

                (
                    func, args, kwargs, result_future, process_future
                ) = await self.tasks.get()

                process_future.set_result(process)

                try:
                    if result_future.done():
                        continue

                    await step(func, args, kwargs, result_future)
                except asyncio.IncompleteReadError:
                    result_future.set_exception(ProcessError(
                        "Process %r exited with code %r" % (
                            process, process.exitcode
                        )
                    ))
                    break
                except Exception as e:
                    if not result_future.done():
                        result_future.set_exception(e)

                    if not writer.is_closing():
                        self.loop.call_soon(writer.close)

                    raise

        task = self.loop.create_task(handler())
        task.add_done_callback(self.task_store.remove)
        self.task_store.add(task)

        self._current_process_event.set()
        await task

    async def start_server(self) -> None:
        self.server = await asyncio.start_server(
            self._handle_client,
            sock=self.socket
        )

        for n in range(self.workers):
            log.debug("Starting worker %d", n)
            await self._respawn_process()

        self.task_store.add(self.loop.create_task(self.supervise()))

    async def _respawn_process(self) -> None:
        log.debug("Spawning new process")
        async with self._create_process_lock:
            self._current_process_event = asyncio.Event()
            self._current_process = self._create_process()
            self.processes.add(self._current_process)
            await self._current_process_event.wait()
            self._current_process_event = None
            self._current_process = None

    async def supervise(self) -> None:
        while True:
            for process in tuple(self.processes):
                if not process.is_alive():
                    log.debug(
                        "Process %r[%d] dead with exitcode %r, respawning",
                        process, process.pid, process.exitcode
                    )
                    self.processes.remove(process)
                    task = self.loop.create_task(self._respawn_process())
                    self.task_store.add(task)
                    task.add_done_callback(self.task_store.remove)

            await asyncio.sleep(0.1)

    def _create_future(self) -> asyncio.Future:
        future = self.loop.create_future()
        self._futures.add(future)
        future.add_done_callback(self._futures.remove)
        return future

    async def _cancel_tasks(self) -> None:
        tasks = set()

        for task in tuple(self.task_store):
            if task.done():
                continue
            task.cancel()
            tasks.add(task)

        await asyncio.gather(*tasks, return_exceptions=True)
        self.task_store.clear()

    async def _reject_futures(self) -> None:
        while self._futures:
            future = self._futures.pop()
            if future.done():
                continue

            future.set_exception(RuntimeError("Pool closed"))
            await asyncio.sleep(0)

    async def close(self) -> None:
        await asyncio.gather(
            self._cancel_tasks(),
            self._reject_futures(),
            return_exceptions=True
        )
        while self.processes:
            process = self.processes.pop()
            process.kill()

    async def create_task(self, func: Callable[..., T],
                          *args: Any, **kwargs: Any) -> T:
        result_future = self._create_future()
        process_future = self._create_future()

        await self.tasks.put((
            func, args, kwargs, result_future, process_future
        ))

        process: Process = await process_future

        try:
            return await result_future
        except asyncio.CancelledError:
            process.kill()

    async def __aenter__(self) -> "WorkerPool":
        await self.start_server()
        return self

    async def __aexit__(self, exc_type: Type[Exception],
                        exc_val: Exception, exc_tb: Traceback) -> None:
        await self.close()
