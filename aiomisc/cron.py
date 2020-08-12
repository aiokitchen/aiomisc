import asyncio
import logging
from datetime import datetime
from functools import partial
from typing import Tuple, Type

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
        "_croniter"
    )

    def __init__(self, coroutine_func, *args, **kwargs):
        self.__name = repr(coroutine_func)
        self._cb = partial(utils.awaitable(coroutine_func), *args, **kwargs)
        self._closed = False
        self._loop = None
        self._handle = None
        self._task = None

        self._croniter = None

    async def _run(self, suppress_exceptions=()):
        try:
            await self._cb()
        except suppress_exceptions:
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Cron task error:")

    def get_next(self):
        if not self._loop or not self._croniter:
            raise asyncio.InvalidStateError
        loop_time = self._loop.time()
        timestamp = datetime.utcnow().timestamp()
        return (
                loop_time +
                (self._croniter.get_next(float) - timestamp)
        )

    def start(
            self,
            spec: str,
            loop=None, *,
            shield: bool = False,
            suppress_exceptions: Tuple[Type[Exception]] = ()
    ):
        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        self._loop = loop or asyncio.get_event_loop()

        self._croniter = croniter(
            spec, start_time=datetime.utcnow().timestamp()
        )

        self._closed = False

        def cron():
            if self._loop.is_closed():
                return

            if self._task and not self._task.done():
                log.warning("Task %r still running skipping", self)
                call_next()
                return

            del self._task
            self._task = None

            if self._closed:
                return

            runner = utils.shield(self._run) if shield else self._run
            self._task = self._loop.create_task(runner(suppress_exceptions))

            call_next()

        def call_next(*_):
            if self._handle is not None:
                self._handle.cancel()
                del self._handle

            self._handle = self._loop.call_at(self.get_next(), cron)

        self._loop.call_at(
            self.get_next(), self._loop.call_soon_threadsafe, cron
        )

    def stop(self):
        self._closed = True

        if self._task is None:
            self._task = self._loop.create_future()
            self._task.set_exception(RuntimeError("Callback not started"))
        elif not self._task.done():
            self._task.cancel()

        if self._handle:
            self._handle.cancel()

        return self._task

    def __repr__(self):
        return "%s(%s)" % (self.__class__.__name__, self.__name)

    def __str__(self):
        return "%s(%s)" % (self.__class__.__name__, self._cb.func.__name__)

    @property
    def task(self):
        return self._task
