from threading import RLock
from typing import Any, Hashable, Optional, Dict, Set
from aiomisc.cache.base import CacheBase


# noinspection PyShadowingBuiltins
class Node:
    __slots__ = 'prev', 'next', 'items'

    def __init__(self, prev: "Node" = None, next: "Node" = None,
                 items: Optional[Set["Item"]] = None):
        self.prev = prev
        self.next = next
        self.items = items or set()


class Item:
    __slots__ = 'node', 'key', 'value'

    def __init__(self, node: Node, key: Hashable, value: Any):
        self.node: Node = node
        self.key: Hashable = key
        self.value: Any = value


class LFUCache(CacheBase):
    """
    LFU cache implementation

    >>> lfu = LFUCache(3)
    >>> lfu.set("foo", "bar")
    >>> assert "foo" in lfu
    >>> lfu.get('foo')
    'bar'

    >>> lfu.remove('foo')
    >>> assert "foo" not in lfu
    >>> lfu.get("foo")
    Traceback (most recent call last):
    ...
    KeyError: 'foo'
    >>> lfu.remove("foo")

    >>> lfu.set("bar", "foo")
    >>> lfu.set("spam", "egg")
    >>> lfu.set("foo", "bar")
    >>> lfu.get("foo")
    'bar'
    >>> lfu.get("spam")
    'egg'
    >>> assert len(lfu) == 3
    >>> lfu.set("egg", "spam")
    >>> assert len(lfu) == 3
    """

    __slots__ = "cache", "usages", "lock"

    def __init__(self, max_size: int):
        super().__init__(max_size)
        self.cache: Dict[Hashable, Item] = dict()
        self.usages: Node = Node(prev=None, next=None)
        self.lock: RLock = RLock()

    def _create_node(self) -> Node:
        node = Node(prev=self.usages, next=None)
        self.usages.next = node
        return node

    def _update_usage(self, item: Item):
        with self.lock:
            old_node = item.node
            new_node = item.node.next

            if new_node is None:
                new_node = self._create_node()

            old_node.items.remove(item)
            item.node = new_node
            new_node.items.add(item)
            self.cache[item.key] = item

            if not old_node.items:
                old_node.next = None
                old_node.prev = None
                self.usages = new_node
                self.usages.prev = None

    def _remove_item(self, item: Item):
        with self.lock:
            if item.key in self.cache:
                self.cache.pop(item.key, None)

            if item in item.node.items:
                item.node.items.remove(item)

            item.node = None

    def get(self, key: Hashable):
        item: Item = self.cache[key]
        self._update_usage(item)
        return item.value

    def remove(self, key: Hashable):
        with self.lock:
            item: Optional[Item] = self.cache.pop(key, None)
            if item is None:
                return

            self._remove_item(item)

    def set(self, key: Hashable, value: Any):
        with self.lock:
            node: Optional[Node] = self.usages

            if node is None:
                node = self._create_node()

            item = Item(node=node, key=key, value=value)
            node.items.add(item)
            self.cache[key] = item

        if self._is_overflow():
            self._on_overflow()

    def _on_overflow(self):
        with self.lock:
            while self._is_overflow():
                if not self.usages.items:
                    if self.usages.next is not None:
                        self.usages.next.prev = None
                        self.usages = self.usages.next
                    else:
                        self.usages = Node(prev=None, next=None)

                item = self.usages.items.pop()
                self._remove_item(item)

    def _is_overflow(self) -> bool:
        return len(self.cache) > self.max_size

    def __contains__(self, key: Hashable) -> Any:
        if key in self.cache:
            self._update_usage(self.cache[key])
            return True
        return False

    def __len__(self):
        return len(self.cache)
