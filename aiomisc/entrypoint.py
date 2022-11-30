import asyncio
import logging
import os
from concurrent.futures import Executor
from typing import (
    Any, Callable, Coroutine, MutableSet, Optional, TypeVar, Union,
)
from weakref import WeakSet

import aiomisc_log
from aiomisc_log import LogLevel

from .compat import event_loop_policy, set_current_loop
from .context import Context, get_context
from .log import LogFormat, basic_config
from .service import Service
from .signal import Signal
from .utils import cancel_tasks, create_default_event_loop


ExecutorType = Executor
T = TypeVar("T")
log = logging.getLogger(__name__)


asyncio_all_tasks = asyncio.all_tasks
asyncio_current_task = asyncio.current_task


def _get_env_bool(name: str, default: str) -> bool:
    enable_variants = {"1", "enable", "enabled", "on", "true", "yes"}
    return os.getenv(name, default).lower() in enable_variants


def _get_env_convert(name: str, converter: Callable[..., T], default: T) -> T:
    value = os.getenv(name)
    if value is None:
        return default
    return converter(value)


class Entrypoint:
    DEFAULT_LOG_LEVEL: str = os.getenv(
        "AIOMISC_LOG_LEVEL", LogLevel.default(),
    )
    DEFAULT_LOG_FORMAT: str = os.getenv(
        "AIOMISC_LOG_FORMAT", LogFormat.default(),
    )

    DEFAULT_AIOMISC_DEBUG: bool = _get_env_bool("AIOMISC_DEBUG", "0")
    DEFAULT_AIOMISC_LOG_CONFIG: bool = _get_env_bool(
        "AIOMISC_LOG_CONFIG", "1",
    )
    DEFAULT_AIOMISC_LOG_FLUSH: float = _get_env_convert(
        "AIOMISC_LOG_FLUSH", float, 0.2,
    )
    DEFAULT_AIOMISC_BUFFERING: bool = _get_env_bool(
        "AIOMISC_LOG_BUFFERING", "1",
    )
    DEFAULT_AIOMISC_BUFFER_SIZE: int = _get_env_convert(
        "AIOMISC_LOG_BUFFER", int, 1024,
    )
    DEFAULT_AIOMISC_POOL_SIZE: Optional[int] = _get_env_convert(
        "AIOMISC_POOL_SIZE", int, None,
    )

    PRE_START = Signal()
    POST_STOP = Signal()
    POST_START = Signal()
    PRE_STOP = Signal()

    async def _start(self) -> None:
        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                buffered=self.log_buffering,
                loop=self.loop,
                buffer_size=self.log_buffer_size,
                flush_interval=self.log_flush_interval,
            )

        set_current_loop(self.loop)

        for signal in (
            self.pre_start, self.post_stop,
            self.pre_stop, self.post_start,
        ):
            signal.freeze()

        await self.pre_start.call(entrypoint=self, services=self.services)

        await asyncio.gather(
            *[self._start_service(svc) for svc in self.services],
        )

        await self.post_start.call(entrypoint=self, services=self.services)

    def __init__(
        self, *services: Service,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        pool_size: Optional[int] = None,
        log_level: Union[int, str] = DEFAULT_LOG_LEVEL,
        log_format: Union[str, LogFormat] = DEFAULT_LOG_FORMAT,
        log_buffering: bool = DEFAULT_AIOMISC_BUFFERING,
        log_buffer_size: int = DEFAULT_AIOMISC_BUFFER_SIZE,
        log_flush_interval: float = DEFAULT_AIOMISC_LOG_FLUSH,
        log_config: bool = DEFAULT_AIOMISC_LOG_CONFIG,
        policy: asyncio.AbstractEventLoopPolicy = event_loop_policy,
        debug: bool = DEFAULT_AIOMISC_DEBUG,
    ):

        """

        :param debug: set debug to event loop
        :param loop: loop
        :param services: Service instances which will be starting.
        :param pool_size: thread pool size
        :param log_level: Logging level which will be configured
        :param log_format: Logging format which will be configured
        :param log_buffer_size: Buffer size for logging
        :param log_flush_interval: interval in seconds for flushing logs
        :param log_config: if False do not configure logging
        """

        self._debug = debug
        self._loop = loop
        self._loop_owner = False
        self._tasks: MutableSet[asyncio.Task] = WeakSet()
        self._thread_pool: Optional[ExecutorType] = None
        self._closing: Optional[asyncio.Event] = None

        self.ctx: Optional[Context] = None
        self.log_buffer_size = log_buffer_size
        self.log_buffering = log_buffering
        self.log_config = log_config
        self.log_flush_interval = log_flush_interval
        self.log_format = log_format
        self.log_level = log_level
        self.policy = policy
        self.pool_size = pool_size
        self.services = services
        self.shutting_down = False
        self.pre_start = self.PRE_START.copy()
        self.post_start = self.POST_START.copy()
        self.pre_stop = self.PRE_STOP.copy()
        self.post_stop = self.POST_STOP.copy()

        if self.log_config:
            aiomisc_log.basic_config(
                level=self.log_level,
                log_format=self.log_format,
            )

        if self._loop is not None:
            set_current_loop(self._loop)

    async def closing(self) -> None:
        # Lazy initialization because event loop might be not exists
        if self._closing is None:
            self._closing = asyncio.Event()

        await self._closing.wait()

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop, self._thread_pool = create_default_event_loop(
                pool_size=self.pool_size,
                policy=self.policy,
                debug=self._debug,
            )
            self._loop_owner = True
            set_current_loop(self._loop)
        return self._loop

    def __del__(self) -> None:
        if self._loop and self._loop.is_closed():
            return

        if self._loop_owner and self._loop is not None:
            self._loop.close()

    def __enter__(self) -> asyncio.AbstractEventLoop:
        self.loop.run_until_complete(self.__aenter__())
        return self.loop

    def __exit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any,
    ) -> None:
        if self.loop.is_closed():
            return

        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                buffered=False,
            )

        self.loop.run_until_complete(
            self.__aexit__(exc_type, exc_val, exc_tb),
        )

        if self._loop_owner and self._loop is not None:
            self._loop.close()

    async def __aenter__(self) -> "Entrypoint":
        if self._loop is None:
            # When __aenter__ called without __enter__
            self._loop = asyncio.get_running_loop()

        self.ctx = Context(loop=self.loop)
        await self._start()
        return self

    async def __aexit__(
        self, exc_type: Any, exc_val: Any, exc_tb: Any,
    ) -> None:
        await self.pre_stop.call(entrypoint=self)

        try:
            if self.loop.is_closed():
                return

            await self.graceful_shutdown(exc_val)
            self.shutting_down = True
        finally:
            if self.ctx:
                self.ctx.close()

            if self._thread_pool:
                self._thread_pool.shutdown()

    async def _start_service(
        self, svc: Service,
    ) -> None:
        svc.set_loop(self.loop)

        start_task, ev_task = map(
            asyncio.ensure_future, (
                svc.start(), svc.start_event.wait(),
            ),
        )

        await asyncio.wait(
            (start_task, ev_task),
            return_when=asyncio.FIRST_COMPLETED,
        )

        self.loop.call_soon(svc.start_event.set)
        await ev_task

        if start_task.done():
            # raise an Exception when failed
            await start_task
            return
        else:
            self._tasks.add(start_task)

        return None

    async def _cancel_background_tasks(self) -> None:
        tasks = asyncio_all_tasks(self._loop)
        current_task = asyncio_current_task(self.loop)
        await cancel_tasks(task for task in tasks if task is not current_task)

    async def graceful_shutdown(self, exception: Exception) -> None:
        if self._closing:
            self._closing.set()

        tasks = []
        for svc in self.services:
            try:
                coro = svc.stop(exception)
            except TypeError as e:
                log.warning(
                    "Failed to stop service %r:\n%r", svc, e,
                )
                log.debug("Service stop failed traceback", exc_info=True)
            else:
                tasks.append(asyncio.shield(coro))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await cancel_tasks(set(self._tasks))

        await self.post_stop.call(entrypoint=self)

        if self._loop_owner:
            await self._cancel_background_tasks()
        await self.loop.shutdown_asyncgens()


entrypoint = Entrypoint


def run(
    coro: Coroutine[None, Any, T],
    *services: Service,
    **kwargs: Any,
) -> T:
    with entrypoint(*services, **kwargs) as loop:
        return loop.run_until_complete(coro)


__all__ = ("entrypoint", "Entrypoint", "get_context", "run")
