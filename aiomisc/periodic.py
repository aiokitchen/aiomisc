import asyncio
import logging
from functools import partial
from typing import Union


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
        self._task = None
        self._loop = None
        self._handle = None

    def start(self, interval: Union[int, float], loop=None):
        if self._closed:
            raise asyncio.InvalidStateError

        self._loop = loop or asyncio.get_event_loop()

        def periodic():
            if self._task and not self._task.done():
                log.warning('Task %r still running skipping', self)
                return

            self._task = self._loop.create_task(self._cb())

            if self._closed:
                return

            self._task.add_done_callback(call)

        def call(*_):
            self._handle = self._loop.call_later(interval, periodic)

        self._loop.call_soon_threadsafe(periodic)

    def stop(self):
        self._closed = True

        if not self._task.done():
            self._task.cancel()

        if self._handle:
            self._handle.cancel()

    def __repr__(self):
        return '%s(%s)' % (self.__class__.__name__, self.__name)
