import asyncio
import logging
import typing as t
from datetime import datetime, timezone
from functools import partial

from croniter import croniter

from . import utils
from .counters import Statistic


log = logging.getLogger(__name__)


class CronCallbackStatistic(Statistic):
    call_count: int
    sum_time: float
    call_ok: int
    call_failed: int
    call_suppressed: int


class CronCallback:
    """
    .. note::

        When the cron function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = (
        "_cb", "_closed", "_task", "_loop", "_handle", "__name",
        "_croniter", "_statistic",
    )

    def __init__(
        self,
        coroutine_func: t.Callable[..., t.Union[t.Any, t.Awaitable[t.Any]]],
        *args: t.Any, **kwargs: t.Any
    ):
        self.__name = repr(coroutine_func)
        self._cb = partial(
            utils.awaitable(coroutine_func), *args, **kwargs
        )
        self._statistic = CronCallbackStatistic()
        self._closed = False
        self._handle = None     # type: t.Optional[asyncio.Handle]
        self._task = None       # type: t.Optional[asyncio.Future]

    async def _run(
        self,
        suppress_exceptions: t.Tuple[t.Type[Exception], ...] = (),
    ) -> None:
        delta = -self._loop.time()
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
            delta += self._loop.time()
            self._statistic.sum_time += delta
            self._statistic.call_count += 1

    def get_next(self) -> float:
        if not self._loop or not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self._loop.time()
        timestamp = datetime.now(timezone.utc).timestamp()
        interval = self._croniter.get_next(float) - timestamp
        if interval < 0:
            raise asyncio.InvalidStateError
        return loop_time + interval

    def get_current(self) -> float:
        if not self._loop or not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self._loop.time()
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
        suppress_exceptions: t.Tuple[t.Type[Exception], ...] = ()
    ) -> None:
        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        current_loop = loop or asyncio.get_event_loop()
        # noinspection PyAttributeOutsideInit
        self._loop = current_loop       # type: asyncio.AbstractEventLoop

        # noinspection PyAttributeOutsideInit
        self._croniter = croniter(
            spec, start_time=datetime.now(timezone.utc).timestamp(),
        )

        self._closed = False

        def cron() -> None:
            if self._loop.is_closed():
                return

            if self._task and not self._task.done():
                log.warning("Task %r still running skipping", self)
                call_next()
                return

            loop = self._loop   # type: asyncio.AbstractEventLoop

            del self._task
            self._task = None

            if self._closed:
                return

            runner = self._run  # type: t.Callable[..., t.Awaitable[t.Any]]
            if shield:
                runner = utils.shield(runner)

            self._task = loop.create_task(runner(suppress_exceptions))

            call_next()

        def call_next(*_: t.Any) -> None:
            if self._handle is not None:
                self._handle.cancel()
                del self._handle

            self._handle = self._loop.call_at(self.get_next(), cron)
        self._loop.call_at(
            self.get_next(), self._loop.call_soon_threadsafe, cron,
        )

    def stop(self) -> asyncio.Future:
        self._closed = True

        if self._task is None:
            self._task = self._loop.create_future()
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
    def task(self) -> t.Optional[asyncio.Future]:
        return self._task
