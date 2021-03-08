from typing import Any

from llist import dllistnode

from .base import CacheBase


class LRUCache(CacheBase):
    def _on_set(self, node: dllistnode) -> None:
        if not self.is_overflow:
            return
        self._on_overflow()

    def _on_get(self, node: dllistnode) -> Any:
        with self.lock:
            self.usages.remove(node)
            self.usages.appendright(node)

    def _on_overflow(self):
        with self.lock:
            while self.is_overflow:
                node: dllistnode = self.usages.popleft()
                item, value = node.value
                self.cache.pop(item)
