import asyncio
import logging
import os
import signal
import sys
from concurrent.futures import Executor
from typing import (
    Any, Callable, Coroutine, FrozenSet, MutableSet, Optional, Set, Tuple,
    TypeVar, Union,
)
from weakref import WeakSet

import aiomisc_log
from aiomisc_log import LogLevel

from ._context_vars import EVENT_LOOP, StrictContextVar
from .compat import event_loop_policy, final
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


class OSSignalHandler:
    def __init__(
        self, sig: int, handler: Callable[[int], None],
    ):
        self.default_handler = signal.getsignal(sig)
        self.signal = sig
        self.handler = handler

    def __callback(self, *_: Any) -> None:
        self.handler(self.signal)

    def apply(self) -> None:
        signal.signal(self.signal, self.__callback)

    def restore(self) -> None:
        signal.signal(self.signal, self.default_handler)


@final
class Entrypoint:
    DEFAULT_LOG_LEVEL: str = os.getenv(
        "AIOMISC_LOG_LEVEL", LogLevel.default(),
    )
    DEFAULT_LOG_FORMAT: str = os.getenv(
        "AIOMISC_LOG_FORMAT", LogFormat.default(),
    )
    DEFAULT_LOG_DATE_FORMAT: Optional[str] = os.getenv(
        "AIOMISC_LOG_DATE_FORMAT",
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
    AIOMISC_SHUTDOWN_TIMEOUT: float = _get_env_convert(
        "AIOMISC_SHUTDOWN_TIMEOUT", float, 60.,
    )

    PRE_START = Signal()
    POST_STOP = Signal()
    POST_START = Signal()
    PRE_STOP = Signal()

    @classmethod
    def get_current(cls) -> "Entrypoint":
        return CURRENT_ENTRYPOINT.get()

    async def _start(self) -> None:
        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                date_format=self.log_date_format,
                buffered=self.log_buffering,
                loop=self.loop,
                buffer_size=self.log_buffer_size,
                flush_interval=self.log_flush_interval,
            )

        CURRENT_ENTRYPOINT.set(self)
        EVENT_LOOP.set(self.loop)

        signals = (
            self.pre_start, self.post_stop, self.pre_stop, self.post_start,
        )

        for sig in signals:
            sig.freeze()

        await self.start_services(*self.__passed_services)
        del self.__passed_services

        for handler in self._signal_handlers:
            handler.apply()

    def __init__(
        self, *services: Service,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        pool_size: Optional[int] = DEFAULT_AIOMISC_POOL_SIZE,
        log_level: Union[int, str] = DEFAULT_LOG_LEVEL,
        log_format: Union[str, LogFormat] = DEFAULT_LOG_FORMAT,
        log_buffering: bool = DEFAULT_AIOMISC_BUFFERING,
        log_buffer_size: int = DEFAULT_AIOMISC_BUFFER_SIZE,
        log_date_format: Optional[str] = DEFAULT_LOG_DATE_FORMAT,
        log_flush_interval: float = DEFAULT_AIOMISC_LOG_FLUSH,
        log_config: bool = DEFAULT_AIOMISC_LOG_CONFIG,
        policy: asyncio.AbstractEventLoopPolicy = event_loop_policy,
        debug: bool = DEFAULT_AIOMISC_DEBUG,
        catch_signals: Tuple[int, ...] = (signal.SIGINT, signal.SIGTERM),
        shutdown_timeout: Union[int, float] = AIOMISC_SHUTDOWN_TIMEOUT,
    ):

        """ Creates a new Entrypoint

        :param debug: set debug to event-loop
        :param loop: loop
        :param services: Service instances which will be starting.
        :param pool_size: thread pool size
        :param log_level: Logging level which will be configured
        :param log_format: Logging format which will be configured
        :param log_buffer_size: Buffer size for logging
        :param log_flush_interval: interval in seconds for flushing logs
        :param log_config: if False do not configure logging
        :param catch_signals: Perform shutdown when this signals will
                              be received
        :param shutdown_timeout: Timeout in seconds for graceful shutdown
        """

        self.__passed_services: FrozenSet[Service] = frozenset(services)

        self._services: Set[Service] = set()
        self._debug = debug
        self._loop = loop
        self._loop_owner = False
        self._tasks: MutableSet[asyncio.Task] = WeakSet()
        self._thread_pool: Optional[ExecutorType] = None
        self._closing: Optional[asyncio.Event] = None

        self._signal_handlers = [
            OSSignalHandler(sig, self._on_interrupt_callback)
            for sig in catch_signals
        ]

        self.catch_signals = catch_signals
        self.shutdown_timeout = float(shutdown_timeout)
        self.ctx: Optional[Context] = None
        self.log_buffer_size = log_buffer_size
        self.log_buffering = log_buffering
        self.log_config = log_config
        self.log_date_format = log_date_format
        self.log_flush_interval = log_flush_interval
        self.log_format = log_format
        self.log_level = log_level
        self.policy = policy

        # signals
        self.pool_size = pool_size
        self.pre_start = self.PRE_START.copy()
        self.post_start = self.POST_START.copy()
        self.pre_stop = self.PRE_STOP.copy()
        self.post_stop = self.POST_STOP.copy()

        if self.log_config:
            aiomisc_log.basic_config(
                level=self.log_level,
                log_format=self.log_format,
                date_format=log_date_format,
            )

        if self._loop is not None:
            EVENT_LOOP.set(self._loop)

        CURRENT_ENTRYPOINT.set(self)

    @property
    def services(self) -> Tuple[Service, ...]:
        return tuple(self._services)

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
            EVENT_LOOP.set(self._loop)
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
        loop = self.loop
        if loop.is_closed():
            return

        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                date_format=self.log_date_format,
                buffered=False,
            )

        loop.run_until_complete(self.__aexit__(exc_type, exc_val, exc_tb))
        if self._loop_owner and self._loop is not None:
            loop.close()

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
        await self._stop(exc_val)

    if sys.version_info < (3, 9):
        async def __shutdown_thread_pool(
            self, loop: asyncio.AbstractEventLoop,
        ) -> None:
            result = self._thread_pool.shutdown()
            if hasattr(result, "__await__"):
                await result
    else:
        def __shutdown_thread_pool(
            self, loop: asyncio.AbstractEventLoop,
        ) -> Coroutine[Any, Any, None]:
            return loop.shutdown_default_executor()

    async def _stop(self, exc: Exception) -> None:
        loop = self.loop

        for handler in self._signal_handlers:
            handler.restore()

        try:
            if loop.is_closed():
                return
            await self.graceful_shutdown(exc)
        finally:
            if self.ctx:
                self.ctx.close()

            if self._thread_pool:
                await self.__shutdown_thread_pool(loop)

    async def _start_service(
        self, svc: Service,
    ) -> None:
        svc.set_loop(self.loop)

        start_task, ev_task = map(
            asyncio.ensure_future, (
                svc.start(), svc.start_event.wait(),
            ),
        )

        self._services.add(svc)

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

    async def start_services(self, *svc: Service) -> None:
        await self.pre_start.call(entrypoint=self, services=svc)
        try:
            await asyncio.gather(*[self._start_service(s) for s in svc])
        finally:
            await self.post_start.call(entrypoint=self, services=svc)

    async def stop_services(
        self, *svc: Service, exc: Optional[Exception] = None,
    ) -> None:
        await self.pre_stop.call(entrypoint=self, services=svc)

        if not svc:
            await self.post_stop.call(entrypoint=self, services=svc)
            return

        tasks = []

        try:
            for s in svc:
                try:
                    log.debug("Stopping service %r", s)
                    coro = s.stop(exc)
                    if hasattr(coro, "__await__"):
                        tasks.append(self.loop.create_task(coro))
                except TypeError as e:
                    log.warning("Failed to stop service %r:\n%r", svc, e)
                    log.debug("Service stop failed traceback", exc_info=True)

            await asyncio.gather(*tasks)
        finally:
            await cancel_tasks(tasks)

            for s in svc:
                self._services.discard(s)

            await self.post_stop.call(entrypoint=self, services=svc)

    async def _cancel_background_tasks(self) -> None:
        tasks = asyncio_all_tasks(self._loop)
        current_task = asyncio_current_task(self.loop)
        await cancel_tasks(task for task in tasks if task is not current_task)

    async def graceful_shutdown(self, exception: Exception) -> None:
        if self._closing:
            self._closing.set()

        await cancel_tasks(set(self._tasks))
        await self.stop_services(*self._services, exc=exception)

        if self._loop_owner:
            await self._cancel_background_tasks()

        await self.loop.shutdown_asyncgens()

    def _on_interrupt_callback(self, _: Any) -> None:
        loop = self.loop
        self.loop.call_soon_threadsafe(self._on_interrupt, loop)

    def _on_interrupt(self, loop: asyncio.AbstractEventLoop) -> None:
        async def shutdown() -> None:
            log.warning("Interrupt signal received, shutting down...")
            try:
                await asyncio.wait_for(
                    self._stop(RuntimeError("Interrupt signal received")),
                    timeout=self.shutdown_timeout,
                )
            except asyncio.TimeoutError as e:
                log.warning(
                    "Shutdown did not happen in %s seconds, aborting.",
                    self.shutdown_timeout,
                )
                # 70 from sysexits.h means "internal software error"
                raise SystemExit(70) from e

        self.loop.create_task(shutdown()).add_done_callback(
            lambda _: loop.stop(),
        )


CURRENT_ENTRYPOINT: StrictContextVar[Entrypoint] = StrictContextVar(
    "CURRENT_ENTRYPOINT",
    RuntimeError("no current entrypoint is set"),
)
entrypoint = Entrypoint


def run(
    coro: Coroutine[None, Any, T],
    *services: Service,
    **kwargs: Any,
) -> T:
    with entrypoint(*services, **kwargs) as loop:
        return loop.run_until_complete(coro)


__all__ = ("entrypoint", "Entrypoint", "get_context", "run")
