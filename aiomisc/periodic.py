import asyncio
import logging
from functools import partial
from typing import Union
from . import utils


log = logging.getLogger(__name__)


class PeriodicCallback:
    """
    .. note::

        When the periodic function executes longer then execution interval a
        next call will be skipping and warning will be logged.

    """

    __slots__ = '_cb', '_closed', '_task', '_loop', '_handle', '__name'

    def __init__(self, coroutine_func, *args, **kwargs):
        self.__name = repr(coroutine_func)
        self._cb = partial(asyncio.coroutine(coroutine_func), *args, **kwargs)
        self._closed = False
        self._loop = None
        self._handle = None
        self._task = None

    async def _run(self):
        try:
            await self._cb()
        except:
            log.exception("Periodic task error:")

    def start(self, interval: Union[int, float],
              loop=None, *, shield: bool = False):

        if self._closed:
            raise asyncio.InvalidStateError

        self._loop = loop or asyncio.get_event_loop()

        def periodic():
            if self._task and not self._task.done():
                log.warning('Task %r still running skipping', self)
                return

            self._task = self._loop.create_task(
                (utils.shield(self._run) if shield else self._run)()
            )

            if self._closed:
                return

            self._task.add_done_callback(call)

        def call(*_):
            self._handle = self._loop.call_later(interval, periodic)

        self._loop.call_soon_threadsafe(periodic)

    def stop(self):
        self._closed = True

        if self._task is None:
            self._task = asyncio.Future(loop=self._loop)
            self._task.set_exception(RuntimeError("Callback not started"))
        elif not self._task.done():
            self._task.cancel()

        if self._handle:
            self._handle.cancel()

        return self._task

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.__name)
