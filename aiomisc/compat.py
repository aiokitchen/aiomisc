import asyncio
import logging
import os
import socket
from collections.abc import Iterator
from importlib.metadata import Distribution, EntryPoint
from time import time_ns
from typing import Any, Concatenate, ParamSpec, Protocol, TypeAlias, final

from ._context_vars import EVENT_LOOP

log = logging.getLogger(__name__)


class EntrypointProtocol(Protocol):
    @property
    def name(self) -> str: ...

    def load(self) -> Any: ...


def entry_pont_iterator(entry_point: str) -> Iterator[EntrypointProtocol]:
    ep: EntryPoint
    for dist in Distribution.discover():
        for ep in dist.entry_points:
            if ep.group == entry_point:
                yield ep


class EventLoopMixin:
    __slots__ = ("_loop",)

    _loop: asyncio.AbstractEventLoop | None

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if not getattr(self, "_loop", None):
            self._loop = asyncio.get_running_loop()
        return self._loop  # type: ignore


# Check if uvloop is available and enabled
_uvloop_module: Any = None
try:
    import uvloop as _uvloop_module_import

    if os.getenv("AIOMISC_USE_UVLOOP", "1").lower() in (
        "yes",
        "1",
        "enabled",
        "enable",
        "on",
        "true",
    ):
        _uvloop_module = _uvloop_module_import
except ImportError:
    pass


class _DefaultEventLoopPolicy:
    """Minimal policy-like object with new_event_loop() method."""

    @staticmethod
    def new_event_loop() -> asyncio.AbstractEventLoop:
        return asyncio.new_event_loop()


# Object with new_event_loop() method - uses uvloop if available
if _uvloop_module is not None:
    event_loop_policy = _uvloop_module
else:
    event_loop_policy = _DefaultEventLoopPolicy()


if hasattr(socket, "TCP_NODELAY"):

    def sock_set_nodelay(sock: socket.socket) -> None:
        if sock.proto != socket.IPPROTO_TCP:
            return None
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
else:

    def sock_set_nodelay(sock: socket.socket) -> None:
        return None


if hasattr(socket, "SO_REUSEPORT"):

    def sock_set_reuseport(sock: socket.socket, reuse_port: bool) -> None:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, reuse_port.real)
else:

    def sock_set_reuseport(sock: socket.socket, reuse_port: bool) -> None:
        log.debug(
            "SO_REUSEPORT is not implemented by underlying library. Skipping."
        )


# 16.x.x reverse compatibility
set_current_loop = EVENT_LOOP.set
get_current_loop = EVENT_LOOP.get

__all__ = (
    "Concatenate",
    "EntrypointProtocol",
    "EventLoopMixin",
    "ParamSpec",
    "Protocol",
    "TypeAlias",
    "entry_pont_iterator",
    "event_loop_policy",
    "final",
    "get_current_loop",
    "set_current_loop",
    "sock_set_nodelay",
    "sock_set_reuseport",
    "time_ns",
)
