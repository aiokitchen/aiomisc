import logging
import os
import socket
from typing import Any, Optional, Tuple

from aiomisc.entrypoint import entrypoint
from aiomisc.periodic import PeriodicCallback
from aiomisc.service.base import Service
from aiomisc.utils import TimeoutType


log = logging.getLogger(__name__)


def _get_watchdog_interval() -> Optional[TimeoutType]:
    value = os.getenv("WATCHDOG_USEC")
    if value is None:
        return None
    return int(value) / 1000000.


WATCHDOG_INTERVAL: Optional[TimeoutType] = _get_watchdog_interval()


class SDWatchdogService(Service):
    socket: socket.socket
    watchdog_interval: Optional[TimeoutType]
    _watchdog_timer: PeriodicCallback

    async def _send(self, payload: str) -> None:
        try:
            await self.loop.sock_sendall(
                self.socket,
                payload.encode(),
            )
        except (ConnectionError, OSError) as e:
            log.warning("SystemD notify socket communication problem: %r", e)

    async def _post_start(
        self, services: Tuple[Service, ...], **__: Any
    ) -> None:
        if not hasattr(self, "socket"):
            return

        await self._send(f"STATUS=Started {len(services)} services")
        await self._send("READY=1")

    async def _pre_stop(self, *_: Any, **__: Any) -> None:
        if not hasattr(self, "socket"):
            return
        await self._send("STOPPING=1")

    def __init__(
        self, *, watchdog_interval: Optional[TimeoutType] = WATCHDOG_INTERVAL,
        **kwargs: Any
    ):
        self.watchdog_interval = watchdog_interval
        entrypoint.POST_START.connect(self._post_start)
        entrypoint.PRE_STOP.connect(self._pre_stop)
        super().__init__(**kwargs)

    @staticmethod
    def _get_socket_addr() -> Optional[str]:
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

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        self.socket.connect(addr)
        self.socket.setblocking(False)

        await self._send("STATUS=starting")

        if self.watchdog_interval is None:
            return

        if self.watchdog_interval != WATCHDOG_INTERVAL:
            watchdog_usec = int(self.watchdog_interval * 1000000)
            await self._send(f"WATCHDOG_USEC={watchdog_usec}")

        self.start_event.set()
        self._watchdog_timer = PeriodicCallback(
            self._send, "WATCHDOG=1",
        )
        # Send notifications twice as often
        self._watchdog_timer.start(self.watchdog_interval / 2)

        # Removing signals from entrypoint factory because the currently
        # running entrypoint instance has been cloned the signals.
        entrypoint.POST_START.disconnect(self._post_start)
        entrypoint.PRE_STOP.disconnect(self._pre_stop)

    async def stop(self, exception: Exception = None) -> Any:
        await self._watchdog_timer.stop()
