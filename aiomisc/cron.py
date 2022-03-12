import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any, Awaitable, Callable, Optional, Tuple, Type, Union

from croniter import croniter

from . import utils
from .compat import EventLoopMixin
from .counters import Statistic


log = logging.getLogger(__name__)


class CronCallbackStatistic(Statistic):
    call_count: int
    sum_time: float
    call_ok: int
    call_failed: int
    call_suppressed: int


class CronCallback(EventLoopMixin):
    """
    .. note::

        When the cron function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = (
        "_cb", "_closed", "_task", "_handle", "__name",
        "_croniter", "_statistic",
    ) + EventLoopMixin.__slots__

    def __init__(
        self,
        coroutine_func: Callable[..., Union[Any, Awaitable[Any]]],
        *args: Any, **kwargs: Any
    ):
        self.__name = repr(coroutine_func)
        self._cb = partial(
            utils.awaitable(coroutine_func), *args, **kwargs
        )
        self._statistic = CronCallbackStatistic()
        self._closed = False
        self._handle: Optional[asyncio.Handle] = None
        self._task: Optional[asyncio.Future] = None

    async def _run(
        self,
        suppress_exceptions: Tuple[Type[Exception], ...] = (),
    ) -> None:
        delta = -self.loop.time()
        try:
            await self._cb()
            self._statistic.call_ok += 1
        except asyncio.CancelledError:
            self._statistic.call_failed += 1
            raise
        except suppress_exceptions:
            self._statistic.call_failed += 1
            self._statistic.call_suppressed += 1
            return
        except Exception:
            self._statistic.call_failed += 1
            log.exception("Cron task error:")
        finally:
            delta += self.loop.time()
            self._statistic.sum_time += delta
            self._statistic.call_count += 1

    def get_next(self) -> float:
        if not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self.loop.time()
        timestamp = datetime.now(timezone.utc).timestamp()
        interval = self._croniter.get_next(float) - timestamp
        if interval < 0:
            raise asyncio.InvalidStateError
        return loop_time + interval

    def get_current(self) -> float:
        if not self.loop or not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self.loop.time()
        timestamp = datetime.now(timezone.utc).timestamp()
        interval = self._croniter.get_current(float) - timestamp
        if interval < 0:
            raise asyncio.InvalidStateError
        return loop_time + interval

    def start(
        self,
        spec: str,
        loop: asyncio.AbstractEventLoop = None,
        *, shield: bool = False,
        suppress_exceptions: Tuple[Type[Exception], ...] = ()
    ) -> None:
        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        self._loop = loop

        # noinspection PyAttributeOutsideInit
        self._croniter = croniter(
            spec, start_time=datetime.now(timezone.utc).timestamp(),
        )

        self._closed = False

        def cron() -> None:
            if self.loop.is_closed():
                return

            if self._task and not self._task.done():
                log.warning("Task %r still running skipping", self)
                call_next()
                return

            del self._task
            self._task = None

            if self._closed:
                return

            runner: Callable[..., Awaitable[Any]] = self._run
            if shield:
                runner = utils.shield(runner)

            self._task = self.loop.create_task(runner(suppress_exceptions))

            call_next()

        def call_next(*_: Any) -> None:
            if self._handle is not None:
                self._handle.cancel()
                del self._handle

            self._handle = self.loop.call_at(self.get_next(), cron)

        self.loop.call_at(
            self.get_next(), self.loop.call_soon_threadsafe, cron,
        )

    def stop(self) -> asyncio.Future:
        self._closed = True

        if self._task is None:
            self._task = self.loop.create_future()
            self._task.set_exception(RuntimeError("Callback not started"))

        elif not self._task.done():
            self._task.cancel()

        if self._handle:
            self._handle.cancel()

        return self._task

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, self.__name)

    def __str__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, self._cb.func.__name__)

    @property
    def task(self) -> Optional[asyncio.Future]:
        return self._task
