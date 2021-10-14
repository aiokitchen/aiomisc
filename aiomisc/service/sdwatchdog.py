import asyncio
import logging
import os
import socket
from collections import deque
from typing import Union, Any, Deque, Tuple, Optional

from .base import Service
from ..entrypoint import entrypoint, Entrypoint
from ..utils import TimeoutType

log = logging.getLogger(__name__)


class AsyncUDPSocket:

    __slots__ = (
        '__loop', '__sock', '__address',
        '__write_queue', '__read_queue',
        '__closed', '__writer_added', '__lock'
    )

    def __init__(
        self, address: Union[tuple, str, bytes], loop: asyncio.AbstractEventLoop
    ):
        self.__loop = loop
        self.__sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.__sock.setblocking(False)
        self.__sock.connect(address)
        self.__writer_added = False
        self.__write_queue: Deque[Tuple[bytes, asyncio.Future]] = deque()
        self.__read_queue: asyncio.Queue = asyncio.Queue()

        self.__loop.add_reader(self.__sock.fileno(), self.__reader)

    async def sendall(self, data: str) -> bool:
        future = self.__loop.create_future()
        self.__write_queue.append((data.encode(), future))

        if not self.__writer_added:
            self.__loop.add_writer(self.__sock.fileno(), self.__sender)
            self.__writer_added = True
        return await future

    def __sender(self) -> None:
        if not self.__write_queue:
            self.__loop.remove_writer(self.__sock.fileno())
            self.__writer_added = False
            return

        data, future = self.__write_queue[0]

        try:
            self.__sock.sendall(data)
        except (BlockingIOError, InterruptedError):
            return
        except BaseException as exc:
            self.__abort(exc)
        else:
            self.__write_queue.popleft()
            future.set_result(True)

    def __abort(self, exc: BaseException) -> None:
        for future in (f for _, f in self.__write_queue if not f.done()):
            future.set_exception(exc)

        self.close()

    async def receive(self) -> bytes:
        return await self.__read_queue.get()

    def __reader(self) -> None:
        self.__read_queue.put_nowait(self.__sock.recv(1024))

    def close(self) -> None:
        self.__loop.remove_writer(self.__sock.fileno())
        self.__sock.close()

        for future in (f for _, f in self.__write_queue if not f.done()):
            future.set_exception(ConnectionError("Connection closed"))

        self.__write_queue.clear()


def _get_watchdog_interval() -> Optional[TimeoutType]:
    value = os.getenv("WATCHDOG_USEC")
    if value is None:
        return None
    # Send notifications twice as often
    return int(value) / 1000000. / 2


WATCHDOG_INTERVAL: Optional[TimeoutType] = _get_watchdog_interval()


class SDWatchdogService(Service):
    socket: AsyncUDPSocket
    watchdog_interval: Optional[TimeoutType]

    async def _post_start(
        self, entrypoint: Entrypoint, services: Tuple[Service, ...]
    ) -> None:
        if not hasattr(self, "socket"):
            return

        await self.socket.sendall(
            "STATUS=Started {} services".format(len(services))
        )
        await self.socket.sendall("READY=1")

    async def _pre_stop(self, *_: Any) -> None:
        if not hasattr(self, "socket"):
            return

        await self.socket.sendall("STOPPING=1")

    def __init__(
        self, *, watchdog_interval: TimeoutType = WATCHDOG_INTERVAL,
        **kwargs: Any
    ):
        self.watchdog_interval = watchdog_interval
        entrypoint.POST_START.connect(self._post_start)
        entrypoint.PRE_STOP.connect(self._pre_stop)
        super().__init__(**kwargs)

    async def start(self) -> None:
        addr = os.getenv('NOTIFY_SOCKET')
        if addr is None:
            log.debug(
                "NOTIFY_SOCKET not exported. Skipping service %r", self
            )
            return None

        if addr[0] == '@':
            addr = '\0' + addr[1:]

        self.socket = AsyncUDPSocket(addr, loop=self.loop)
        self.loop.call_soon(self.start_event.set)

        await self.socket.sendall("STATUS=starting")

        if self.watchdog_interval is None:
            return

        self.start_event.set()
        await asyncio.gather(self.__watchdog(), self.__reader())

    async def __watchdog(self) -> None:
        while True:
            await self.socket.sendall("WATCHDOG=1")
            await asyncio.sleep(self.watchdog_interval)

    async def __reader(self) -> None:
        while True:
            log.debug("[%r] Received %r", self, await self.socket.receive())
