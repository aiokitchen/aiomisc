import asyncio
from functools import partial
from typing import Union


class PeriodicCallback:
    __slots__ = '_cb', '_closed', '_task', '_loop', '_handle'

    def __init__(self, coroutine_func, *args, **kwargs):
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
