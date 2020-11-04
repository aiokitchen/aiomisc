import asyncio
import logging
import typing as t
from functools import partial

from . import utils


log = logging.getLogger(__name__)
ExceptionsType = t.Tuple[t.Type[Exception], ...]
CallbackType = t.Callable[..., t.Union[t.Awaitable[t.Any], t.Any]]


class PeriodicCallback:
    """
    .. note::

        When the periodic function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = "_cb", "_closed", "_task", "_loop", "_handle", "__name"

    def __init__(
        self, coroutine_func: CallbackType,
        *args: t.Any, **kwargs: t.Any
    ):

        self.__name = repr(coroutine_func)
        self._cb = partial(
            utils.awaitable(coroutine_func), *args, **kwargs
        )
        self._closed = False    # type: t.Optional[bool]
        self._handle = None     # type: t.Optional[asyncio.Handle]
        self._task = None       # type: t.Optional[asyncio.Future]

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
        self, interval: t.Union[int, float],
        loop: asyncio.AbstractEventLoop = None, *,
        delay: t.Union[int, float] = 0,
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

            self._task.add_done_callback(call)

        def call(*_: t.Any) -> None:
            if self._handle is not None:
                self._handle.cancel()
                del self._handle

            self._handle = self._loop.call_later(
                interval, periodic,
            )

        self._loop.call_later(delay, self._loop.call_soon_threadsafe, periodic)

    def stop(self) -> asyncio.Task:
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
    def task(self) -> asyncio.Task:
        return self._task   # type: ignore
