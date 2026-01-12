import logging
import os
import socket
from collections.abc import Iterable, Iterator
from typing import Any

from aiomisc.compat import get_current_loop
from aiomisc.periodic import PeriodicCallback
from aiomisc.service.base import Service
from aiomisc.thread_pool import threaded
from aiomisc.utils import TimeoutType

log = logging.getLogger(__name__)


def _get_watchdog_interval() -> TimeoutType | None:
    value = os.getenv("WATCHDOG_USEC")
    if value is None:
        return None
    return int(value) / 1000000.0


def _get_socket_addr() -> str | None:
    addr = os.getenv("NOTIFY_SOCKET")
    if addr is None:
        return None
    if addr[0] == "@":
        addr = "\0" + addr[1:]
    return addr


WATCHDOG_INTERVAL: TimeoutType | None = _get_watchdog_interval()


class SDWatchdogService(Service):
    socket: socket.socket
    socket_addr: str | None
    watchdog_interval: TimeoutType | None = None
    watchdog_timer: PeriodicCallback
    name: str = "systemd-watchdog"

    def __init__(
        self,
        watchdog_interval: TimeoutType | None = WATCHDOG_INTERVAL,
        **kwargs: Any,
    ):
        self.watchdog_interval = watchdog_interval
        self.socket_addr = _get_socket_addr()

        super().__init__(**kwargs)

    @property
    def is_connected(self) -> bool:
        return hasattr(self, "socket")

    async def send(self, payload: str) -> None:
        if not self.is_connected:
            return

        try:
            await self.loop.sock_sendall(self.socket, payload.encode())
        except (ConnectionError, OSError) as e:
            log.warning("SystemD notify socket communication problem: %r", e)

    @threaded
    def connect(self) -> bool:
        if self.socket_addr is None:
            return False

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.connect(self.socket_addr)
        self.socket.setblocking(False)
        return True

    @threaded
    def disconnect(self) -> None:
        if not self.is_connected:
            return

        sock = self.socket
        del self.socket

        self.socket_addr = None
        sock.close()

    async def start(self) -> None:
        self.watchdog_timer = PeriodicCallback(
            self.send, "WATCHDOG=1", name=self.name
        )

        if self.is_connected and self.watchdog_interval is not None:
            if self.watchdog_interval != WATCHDOG_INTERVAL:
                watchdog_usec = int(self.watchdog_interval * 1000000)
                await self.send(f"WATCHDOG_USEC={watchdog_usec}")

            self.start_event.set()

            # Send notifications twice as often
            self.watchdog_timer.start(self.watchdog_interval / 2)

    async def stop(self, exception: Exception | None = None) -> None:
        await self.watchdog_timer.stop(return_exceptions=True)


def filter_services(services: Iterable[Service]) -> Iterator[SDWatchdogService]:
    for service in services:
        if not isinstance(service, SDWatchdogService):
            continue
        yield service


async def _pre_start(*, services: tuple[Service, ...], **__: Any) -> None:
    for service in filter_services(services):
        if not service.socket_addr:
            log.debug(
                "NOTIFY_SOCKET not exported. Skipping service %r", service
            )
            continue

        service.set_loop(get_current_loop())

        if await service.connect():
            await service.send(f"STATUS=Starting {len(services)} services")


async def _post_start(*, services: tuple[Service, ...], **__: Any) -> None:
    for service in filter_services(services):
        await service.send(f"STATUS=Started {len(services)} services")
        await service.send("READY=1")


async def _pre_stop(*, services: tuple[Service, ...], **__: Any) -> None:
    for service in filter_services(services):
        await service.send(f"STATUS=Stopping {len(services)} services")


async def _post_stop(*, services: tuple[Service, ...], **_: Any) -> None:
    for service in filter_services(services):
        await service.send("STOPPING=1")
        await service.disconnect()


def setup() -> None:
    from aiomisc.entrypoint import entrypoint

    entrypoint.PRE_START.connect(_pre_start)
    entrypoint.POST_START.connect(_post_start)
    entrypoint.PRE_STOP.connect(_pre_stop)
    entrypoint.POST_STOP.connect(_post_stop)


__all__ = ("SDWatchdogService",)
__doc__ = "Adds SystemD watchdog support to the entrypoint."
