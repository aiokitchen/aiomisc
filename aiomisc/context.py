import asyncio
from collections import defaultdict


class Context:
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
        def setter(future: asyncio.Future):
            if future.done():
                self._storage.pop(future)

            future.set_result(value)

        self._loop.call_soon_threadsafe(setter, self._storage[item])


def get_context(loop: asyncio.AbstractEventLoop = None) -> Context:
    loop = loop or asyncio.get_event_loop()

    if loop.is_closed():
        raise RuntimeError('event loop is closed')

    return Context._EVENT_OBJECTS[loop]


__all__ = ('get_context', 'Context')
