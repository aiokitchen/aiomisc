import asyncio
from collections import defaultdict


class Context:
    __slots__ = ('_storage', '_loop')

    _EVENT_OBJECTS = dict()

    def close(self):
        self._storage.clear()
        self._EVENT_OBJECTS.pop(self._loop, None)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._storage = defaultdict(loop.create_future)
        self._EVENT_OBJECTS[loop] = self

    def __getitem__(self, item):
        return self._storage[item]

    def __setitem__(self, item, value):
        self._loop.call_soon_threadsafe(self.__setter, item, value)

    def __setter(self, item, value):
        if self._storage[item].done():
            del self._storage[item]

        self._storage[item].set_result(value)


def get_context(loop: asyncio.AbstractEventLoop = None) -> Context:
    loop = loop or asyncio.get_event_loop()

    if loop.is_closed():
        raise RuntimeError('event loop is closed')

    return Context._EVENT_OBJECTS[loop]


__all__ = ('get_context', 'Context')
