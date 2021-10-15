import asyncio
import logging
from functools import partial
from typing import Any, Awaitable, Callable, Optional, Tuple, Type, Union

from . import utils
from .counters import Statistic


log = logging.getLogger(__name__)
ExceptionsType = Tuple[Type[Exception], ...]
CallbackType = Callable[..., Union[Awaitable[Any], Any]]


class PeriodicCallbackStatistic(Statistic):
    call_count: int
    done: int
    fail: int
    sum_time: float


class PeriodicCallback:
    """
    .. note::

        When the periodic function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = (
        "_cb", "_closed", "_task", "_loop", "_handle", "__name",
        "_statistic",
    )

    _closed: Optional[bool]
    _handle: Optional[asyncio.Handle]
    _task: Optional[asyncio.Future]

    def __init__(
        self, coroutine_func: CallbackType,
        *args: Any, **kwargs: Any
    ):

        self._statistic = PeriodicCallbackStatistic()
        self.__name = repr(coroutine_func)
        self._cb = partial(
            utils.awaitable(coroutine_func), *args, **kwargs
        )
        self._closed = False
        self._handle = None
        self._task = None

    async def _run(self, suppress_exceptions: ExceptionsType = ()) -> None:
        try:
            await self._cb()
        except suppress_exceptions:
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Periodic task error:")

    def start(
        self, interval: Union[int, float],
        loop: asyncio.AbstractEventLoop = None, *,
        delay: Union[int, float] = 0,
        shield: bool = False,
        suppress_exceptions: ExceptionsType = ()
    ) -> None:
        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        current_loop = loop or asyncio.get_event_loop()
        # noinspection PyAttributeOutsideInit
        self._loop = current_loop   # type: asyncio.AbstractEventLoop
        self._closed = False

        def periodic() -> None:
            if self._loop.is_closed():
                return

            if self._task and not self._task.done():
                log.warning("Task %r still running skipping", self)
                return

            del self._task
            self._task = None

            if self._closed:
                return

            runner = utils.shield(self._run) if shield else self._run
            self._task = self._loop.create_task(
                runner(suppress_exceptions),        # type: ignore
            )

            start_time = self._loop.time()

            self._task.add_done_callback(call)
            self._task.add_done_callback(lambda t: do_stat(t, start_time))

        def do_stat(task: asyncio.Task, start_time: float) -> None:
            self._statistic.call_count += 1
            self._statistic.sum_time += self._loop.time() - start_time

            if task.cancelled():
                self._statistic.fail += 1
            elif task.exception():
                self._statistic.fail += 1
            else:
                self._statistic.done += 1

        def call(*_: Any) -> None:
            if self._handle is not None:
                self._handle.cancel()
                del self._handle

            self._handle = self._loop.call_later(
                interval, periodic,
            )

        self._loop.call_later(delay, self._loop.call_soon_threadsafe, periodic)

    def stop(self) -> asyncio.Future:
        self._closed = True

        if self._task is None:
            self._task = self._loop.create_future()
            self._task.set_exception(
                RuntimeError("Callback not started"),
            )
        elif not self._task.done():
            self._task.cancel()

        if self._handle:
            self._handle.cancel()

        return self.task

    def __repr__(self) -> str:
        return "%s(%s)" % (self.__class__.__name__, self.__name)

    @property
    def task(self) -> asyncio.Future:
        return self._task   # type: ignore
