import asyncio
import logging
import typing

from .context import Context, get_context
from .log import LogFormat, basic_config
from .service import Service
from .signal import Signal
from .utils import create_default_event_loop, event_loop_policy


class Entrypoint:

    PRE_START = Signal()
    POST_STOP = Signal()

    async def _start(self):
        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                buffered=True,
                loop=self.loop,
                buffer_size=self.log_buffer_size,
                flush_interval=self.log_flush_interval,
            )

        for signal in (self.pre_start, self.post_stop):
            signal.freeze()

        await self.pre_start.call(entrypoint=self, services=self.services)

        await asyncio.gather(
            *[self._start_service(svc) for svc in self.services],
        )

    def __init__(
        self, *services, loop: asyncio.AbstractEventLoop = None,
        pool_size: int = None,
        log_level: typing.Union[int, str] = logging.INFO,
        log_format: typing.Union[str, LogFormat] = "color",
        log_buffer_size: int = 1024,
        log_flush_interval: float = 0.2,
        log_config: bool = True,
        policy=event_loop_policy,
        debug: bool = False
    ):

        """

        :param debug: set debug to event loop
        :param loop: loop
        :param services: Service instances which will be starting.
        :param pool_size: thread pool size
        :param log_level: Logging level which will be configured
        :param log_format: Logging format which will be configures
        :param log_buffer_size: Buffer size for logging
        :param log_flush_interval: interval in seconds for flushing logs
        :param log_config: if False do not configure logging
        """

        self._debug = debug
        self._loop = loop
        self._loop_owner = False
        self._thread_pool = None
        self.ctx = None
        self.log_buffer_size = log_buffer_size
        self.log_config = log_config
        self.log_flush_interval = log_flush_interval
        self.log_format = log_format
        self.log_level = log_level
        self.policy = policy
        self.pool_size = pool_size
        self.services = services
        self.shutting_down = False
        self.pre_start = self.PRE_START.copy()
        self.post_stop = self.POST_STOP.copy()

        self._closing = None

    async def closing(self):
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

        return self._loop

    def __del__(self):
        if self._loop and self._loop.is_closed():
            return

        if self._loop_owner:
            self._loop.close()

    def __enter__(self) -> asyncio.AbstractEventLoop:
        self.loop.run_until_complete(self.__aenter__())
        return self.loop

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.loop.is_closed():
            return

        self.loop.run_until_complete(
            self.__aexit__(exc_type, exc_val, exc_tb),
        )

        if self._loop_owner:
            self._loop.close()

    async def __aenter__(self) -> "Entrypoint":
        if self._loop is None:
            # When __aenter__ called without __enter__
            self._loop = asyncio.get_event_loop()

        if self.log_config:
            basic_config(
                level=self.log_level,
                log_format=self.log_format,
                loop=self.loop,
                buffered=False,
            )

        self.ctx = Context(loop=self.loop)
        await self._start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if self.loop.is_closed():
                return

            await self.graceful_shutdown(exc_val)
            self.shutting_down = True
        finally:
            self.ctx.close()

            if self._thread_pool:
                self._thread_pool.shutdown()

    async def _start_service(self, svc: Service):
        svc.set_loop(self.loop)

        start_task, ev_task = map(
            asyncio.ensure_future, (svc.start(), svc.start_event.wait()),
        )

        await asyncio.wait(
            (start_task, ev_task),
            return_when=asyncio.FIRST_COMPLETED,
        )

        self.loop.call_soon(svc.start_event.set)
        await ev_task

        if start_task.done():
            return await start_task

    async def graceful_shutdown(self, exception):
        if self._closing:
            self._closing.set()

        tasks = [
            asyncio.shield(svc.stop(exception)) for svc in self.services
        ]

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        await self.post_stop.call(entrypoint=self)
        await self.loop.shutdown_asyncgens()


entrypoint = Entrypoint


__all__ = ("entrypoint", "Entrypoint", "get_context")
