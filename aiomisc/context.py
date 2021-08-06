import asyncio
import typing as t
from collections import defaultdict

from aiomisc.counters import Statistic


_StorageType = t.DefaultDict[t.Any, asyncio.Future]
_EventObjectStoreType = t.Dict[
    asyncio.AbstractEventLoop, "Context",
]


class ContextStatistic(Statistic):
    get: int
    set: int


class Context:
    __slots__ = ("_storage", "_loop", "_statistic")

    _EVENT_OBJECTS = dict()     # type: _EventObjectStoreType

    def close(self) -> None:
        self._storage.clear()
        self._EVENT_OBJECTS.pop(self._loop, None)

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._storage = defaultdict(loop.create_future)  # type: _StorageType
        self._EVENT_OBJECTS[loop] = self
        self._statistic = ContextStatistic()

    def __getitem__(self, item: t.Any) -> t.Any:
        self._statistic.get += 1
        return self._storage[item]

    def __setitem__(self, item: t.Any, value: t.Any) -> None:
        self._statistic.set += 1
        self._loop.call_soon_threadsafe(self.__setter, item, value)

    def __setter(self, item: t.Any, value: t.Any) -> None:
        if self._storage[item].done():
            del self._storage[item]

        self._storage[item].set_result(value)


def get_context(loop: asyncio.AbstractEventLoop = None) -> Context:
    loop = loop or asyncio.get_event_loop()

    if loop.is_closed():
        raise RuntimeError("event loop is closed")

    return Context._EVENT_OBJECTS[loop]


__all__ = ("get_context", "Context")
