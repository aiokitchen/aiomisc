import asyncio
import logging
import os
import socket
from collections.abc import Callable, Iterator
from importlib.metadata import Distribution, EntryPoint
from time import time_ns
from typing import Any, Concatenate, ParamSpec, Protocol, TypeAlias, TypeVar, final


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


LoopFactoryType = Callable[[], asyncio.AbstractEventLoop]
T = TypeVar("T")

# Use native asyncio.Runner (Python 3.11+)
Runner = asyncio.Runner


def default_loop_factory() -> asyncio.AbstractEventLoop:
    """Default loop factory - uses uvloop if available, otherwise asyncio."""
    if _uvloop_module is not None:
        return _uvloop_module.new_event_loop()
    return asyncio.new_event_loop()


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


__all__ = (
    "Concatenate",
    "EntrypointProtocol",
    "EventLoopMixin",
    "LoopFactoryType",
    "ParamSpec",
    "Protocol",
    "Runner",
    "TypeAlias",
    "default_loop_factory",
    "entry_pont_iterator",
    "final",
    "sock_set_nodelay",
    "sock_set_reuseport",
    "time_ns",
)
