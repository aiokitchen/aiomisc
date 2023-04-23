import asyncio
import logging
from typing import Any, Optional, Union

from .compat import EventLoopMixin
from .recurring import CallbackType, ExceptionsType, RecurringCallback


log = logging.getLogger(__name__)


class PeriodicCallback(EventLoopMixin):
    """
    .. note::

        When the periodic function executes longer then execution interval a
        next call would be skipped and warning would be logged.

    """

    __slots__ = ("_recurring_callback", "_task") + EventLoopMixin.__slots__

    _task: Optional[asyncio.Future]

    def __init__(
        self, coroutine_func: CallbackType, *args: Any, **kwargs: Any,
    ):
        self._recurring_callback: RecurringCallback = RecurringCallback(
            coroutine_func, *args, **kwargs,
        )
        self._task: Optional[asyncio.Task] = None

    def start(
        self, interval: Union[int, float],
        loop: Optional[asyncio.AbstractEventLoop] = None, *,
        delay: Union[int, float] = 0,
        shield: bool = False,
        suppress_exceptions: ExceptionsType = (),
    ) -> None:
        assert interval

        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        delayed = False

        def strategy(_: Any) -> Union[int, float]:
            nonlocal delayed
            if not delayed:
                delayed = True
                return delay
            return interval

        self._task = self._recurring_callback.start(
            strategy=strategy,
            shield=shield,
            loop=loop,
            suppress_exceptions=suppress_exceptions,
        )

        def clean_task(_: Any) -> None:
            self._task = None

        self._task.add_done_callback(clean_task)

    def stop(self, return_exceptions: bool = False) -> asyncio.Future:
        if self._task is None:
            self._task = self.loop.create_future()
            self._task.set_exception(RuntimeError("Callback not started"))
        elif not self._task.done():
            self._task.cancel()
        task, self._task = self._task, None
        return asyncio.gather(task, return_exceptions=return_exceptions)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self._recurring_callback.name})"
