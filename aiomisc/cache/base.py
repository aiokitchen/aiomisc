import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Any, Union, Hashable, Dict, Optional

from llist import dllist, dllistnode


class CacheBase(ABC):
    def __init__(self, max_size: int = 0):
        self._max_size: int = max_size
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.usages: dllist = dllist()
        self.cache: Dict[Hashable, Any] = dict()
        self.lock = threading.RLock()

    @property
    def is_overflow(self) -> bool:
        if self._max_size == 0:
            return False

        if self._max_size < len(self.usages):
            return True

        return False

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            self._loop = asyncio.get_event_loop()
        return self._loop

    @abstractmethod
    def _on_set(self, node: dllistnode) -> None:
        pass

    def _on_expires(self, node: dllistnode) -> None:
        pass

    @abstractmethod
    def _on_get(self, node: dllistnode) -> Any:
        pass

    def __contains__(self, item: Hashable) -> bool:
        return item in self.cache

    def get(self, item: Hashable) -> Any:
        with self.lock:
            node: dllistnode = self.cache[item]
        self.loop.call_soon(self._on_get, node)
        return node.value[1]

    def expire(self, node: dllistnode):
        with self.lock:
            item, value = node.value
            node: Optional[dllistnode] = self.cache.pop(item, None)

        if node is None:
            return

        self.loop.call_soon(self._on_expires, node)
        self.usages.remove(node)

    def set(self, item: Hashable, value: Any,
            expiration: Union[int, float] = None) -> None:
        with self.lock:
            node: dllistnode = self.usages.append((item, value))
            self.cache[item] = node

        self.loop.call_soon(self._on_set, node)

        if expiration is not None:
            self.loop.call_later(expiration, self.expire, node)
