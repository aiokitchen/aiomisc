import asyncio
import logging
from datetime import datetime, timezone
from functools import partial
from typing import Any, Awaitable, Callable, Optional, Tuple, Type, Union

from croniter import croniter

from .compat import EventLoopMixin
from .recurring import RecurringCallback


log = logging.getLogger(__name__)


class CronCallback(EventLoopMixin):
    """
    .. note::

        When the cron function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = ("_recurring_cb", "_task") + EventLoopMixin.__slots__

    def __init__(
        self,
        coroutine_func: Callable[..., Union[Any, Awaitable[Any]]],
        *args: Any, **kwargs: Any,
    ):
        self._recurring_cb = RecurringCallback(
            coroutine_func, *args, **kwargs,
        )
        self._task: Optional[asyncio.Task] = None

    @staticmethod
    def get_next(cron: croniter, _: RecurringCallback) -> float:
        timestamp = datetime.now(timezone.utc).timestamp()
        next_date = cron.get_next(float, timestamp)
        return next_date - timestamp

    def start(
        self,
        spec: str,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        *, shield: bool = False,
        suppress_exceptions: Tuple[Type[Exception], ...] = (),
    ) -> None:
        if self._task and not self._task.done():
            raise asyncio.InvalidStateError

        self._loop = loop

        # noinspection PyAttributeOutsideInit
        strategy = partial(self.get_next, croniter(spec))

        self._task = self._recurring_cb.start(
            strategy=strategy,
            loop=loop,
            shield=shield,
            suppress_exceptions=suppress_exceptions,
        )

    def stop(self) -> asyncio.Future:
        if self._task is None:
            task = self.loop.create_future()
            task.set_exception(RuntimeError("Callback not started"))
            return task

        elif not self._task.done():
            self._task.cancel()
        return self._task

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}({self._recurring_cb.name})>"
