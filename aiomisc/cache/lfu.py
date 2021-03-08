from dataclasses import dataclass
from threading import RLock
from typing import Any, Hashable, Optional

from llist import dllistnode, dllist


@dataclass(frozen=True)
class FrequencyItem:
    node: dllistnode
    key: Hashable
    value: Any


class LFUCache:
    """
    LFU cache implementation

    >>> lfu = LFUCache(3)
    >>> lfu.set("foo", "bar")
    >>> assert "foo" in lfu
    >>> lfu.get('foo')
    'bar'
    >>> lfu.set("bar", "foo")
    >>> lfu.set("spam", "egg")

    """

    def __init__(self, max_size: int = 0):
        self.cache = dict()
        self.usages = dllist()
        self.lock = RLock()
        self.size = 0
        self.max_size = max_size

    def _create_node(self) -> dllistnode:
        return self.usages.append(set([]))

    def _update_usage(self, item: FrequencyItem):
        with self.lock:
            old_node = item.node
            new_node = item.node.next

            if new_node is None:
                new_node = self._create_node()

            old_node.value.remove(item)
            item = FrequencyItem(
                node=new_node,
                key=item.key,
                value=item.value,
            )
            new_node.value.add(item)
            self.cache[item.key] = item

            if not old_node.value:
                self.usages.remove(old_node)

    def get(self, key: Hashable):
        item: FrequencyItem = self.cache[key]
        self._update_usage(item)
        return item.value

    def set(self, key: Hashable, value: Any):
        with self.lock:
            node: Optional[dllistnode] = self.usages.first

            if node is None:
                node = self._create_node()

            item = FrequencyItem(node=node, key=key, value=value)
            node.value.add(item)
            self.cache[key] = item

    def __contains__(self, key) -> Any:
        if key in self.cache:
            self._update_usage(self.cache[key])
            return True
        return False
