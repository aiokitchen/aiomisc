import asyncio
import logging
import typing as t
from datetime import datetime
from functools import partial

from croniter import croniter

from . import utils


log = logging.getLogger(__name__)


class CronCallback:
    """
    .. note::

        When the cron function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = (
        "_cb", "_closed", "_task", "_loop", "_handle", "__name",
        "_croniter",
    )

    def __init__(
        self, coroutine_func: t.Callable[..., t.Awaitable[t.Any]],
        *args: t.Any, **kwargs: t.Any
    ):
        self.__name = repr(coroutine_func)
        self._cb = partial(
            utils.awaitable(coroutine_func), *args, **kwargs
        )    # type: ignore
        self._closed = False
        self._handle = None     # type: t.Optional[asyncio.Handle]
        self._task = None       # type: t.Optional[asyncio.Future]

    async def _run(
        self,
        suppress_exceptions: t.Tuple[t.Type[Exception], ...] = ()
    ) -> None:
        try:
            await self._cb()
        except asyncio.CancelledError:
            raise
        except suppress_exceptions:
            return
        except Exception:
            log.exception("Cron task error:")

    def get_next(self) -> float:
        if not self._loop or not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self._loop.time()
        timestamp = datetime.utcnow().timestamp()
        return (
            loop_time + (self._croniter.get_next(float) - timestamp)
        )

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
            spec, start_time=datetime.utcnow().timestamp(),
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
