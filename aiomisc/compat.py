import asyncio
import logging
import socket
from functools import partial
from typing import Any, Callable, Optional, TypeVar


log = logging.getLogger(__name__)


try:
    # noinspection PyUnresolvedReferences
    import contextvars

    T = TypeVar("T")
    F = TypeVar("F", bound=Callable[..., Any])

    def context_partial(
        func: F, *args: Any,
        **kwargs: Any
    ) -> Any:
        context = contextvars.copy_context()
        return partial(context.run, func, *args, **kwargs)
except ImportError:
    context_partial = partial   # type: ignore


try:
    from time import time_ns
except ImportError:
    from time import time

    def time_ns() -> int:
        return int(time() * 1000000000)


try:
    from queue import SimpleQueue
except ImportError:
    from queue import Queue as SimpleQueue  # type: ignore


def _get_running_loop_backport() -> asyncio.AbstractEventLoop:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        return loop
    raise RuntimeError("no running event loop")


get_running_loop = getattr(
    asyncio, "get_running_loop", _get_running_loop_backport,
)


class EventLoopMixin:
    __slots__ = "_loop",

    _loop: Optional[asyncio.AbstractEventLoop]

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if not getattr(self, "_loop", None):
            self._loop = get_running_loop()
        return self._loop   # type: ignore


try:
    import uvloop  # type: ignore
    event_loop_policy = uvloop.EventLoopPolicy()
except ImportError:
    event_loop_policy = asyncio.DefaultEventLoopPolicy()


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
        sock.setsockopt(
            socket.SOL_SOCKET, socket.SO_REUSEPORT, reuse_port.real,
        )
else:
    def sock_set_reuseport(sock: socket.socket, reuse_port: bool) -> None:
        log.debug(
            "SO_REUSEPORT is not implemented by "
            "underlying library. Skipping.",
        )


try:
    from contextvars import ContextVar
    EVENT_LOOP: ContextVar = ContextVar("EVENT_LOOP")

    def get_current_loop() -> asyncio.AbstractEventLoop:
        loop: Optional[asyncio.AbstractEventLoop] = EVENT_LOOP.get(None)
        if loop is None:
            raise RuntimeError("no current event loop is set")
        return loop

    def set_current_loop(loop: asyncio.AbstractEventLoop) -> None:
        EVENT_LOOP.set(loop)

except ImportError:
    def get_current_loop() -> asyncio.AbstractEventLoop:
        raise RuntimeError("contextvars module is not installed")

    def set_current_loop(loop: asyncio.AbstractEventLoop) -> None:
        return


__all__ = (
    "EventLoopMixin",
    "SimpleQueue",
    "context_partial",
    "event_loop_policy",
    "get_current_loop",
    "set_current_loop",
    "get_running_loop",
    "sock_set_nodelay",
    "sock_set_reuseport",
    "time_ns",
)
