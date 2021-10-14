import asyncio
import logging
import os
import socket
from collections import deque
from typing import Any, Deque, Optional, Tuple, Union

from aiomisc.entrypoint import entrypoint
from aiomisc.periodic import PeriodicCallback
from aiomisc.service.base import Service
from aiomisc.utils import TimeoutType


log = logging.getLogger(__name__)


class AsyncUDPSocket:

    __slots__ = (
        "__address",
        "__lock",
        "__loop",
        "__sock",
        "__write_queue",
        "__writer_added",
    )

    def __init__(
        self, address: Union[tuple, str, bytes],
        loop: asyncio.AbstractEventLoop,
    ):
        self.__loop = loop
        self.__sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.__sock.setblocking(False)
        self.__sock.connect(address)
        self.__writer_added = False
        self.__write_queue: Deque[Tuple[bytes, asyncio.Future]] = deque()

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
    _watchdog_timer: PeriodicCallback

    async def _post_start(
        self, services: Tuple[Service, ...], **__: Any
    ) -> None:
        if not hasattr(self, "socket"):
            return
        await self.socket.sendall(
            "STATUS=Started {} services".format(len(services)),
        )
        await self.socket.sendall("READY=1")

    async def _pre_stop(self, *_: Any, **__: Any) -> None:
        if not hasattr(self, "socket"):
            return
        await self.socket.sendall("STOPPING=1")

    def __init__(
        self, *, watchdog_interval: Optional[TimeoutType] = WATCHDOG_INTERVAL,
        **kwargs: Any
    ):
        self.watchdog_interval = watchdog_interval
        entrypoint.POST_START.connect(self._post_start)
        entrypoint.PRE_STOP.connect(self._pre_stop)
        super().__init__(**kwargs)

    def _get_socket_addr(self) -> Optional[str]:
        addr = os.getenv("NOTIFY_SOCKET")
        if addr is None:
            return None

        if addr[0] == "@":
            addr = "\0" + addr[1:]

        return addr

    async def start(self) -> None:
        addr = self._get_socket_addr()
        if addr is None:
            log.debug(
                "NOTIFY_SOCKET not exported. Skipping service %r", self,
            )
            return None

        self.socket = AsyncUDPSocket(addr, loop=self.loop)
        await self.socket.sendall("STATUS=starting")

        if self.watchdog_interval is None:
            return

        if self.watchdog_interval != WATCHDOG_INTERVAL:
            await self.socket.sendall(
                "WATCHDOG_USEC={}".format(
                    int(self.watchdog_interval * 1000000),
                ),
            )

        self.start_event.set()
        self._watchdog_timer = PeriodicCallback(
            self.socket.sendall,
            "WATCHDOG=1",
        )
        self._watchdog_timer.start(self.watchdog_interval)

    async def stop(self, exception: Exception = None) -> Any:
        await self._watchdog_timer.stop()
