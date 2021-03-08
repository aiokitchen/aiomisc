from dataclasses import dataclass
from threading import RLock
from typing import Any, Hashable, Optional, Set


class Node:
    __slots__ = ('prev', 'next', 'items')

    def __init__(self, prev: "Node" = None, next: "Node" = None,
                 items: Optional[Set["Item"]] = None):
        self.prev = prev
        self.next = next
        self.items = items or set()


@dataclass(frozen=True)
class Item:
    node: Node
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
        self.usages: Node = Node(prev=None, next=None, items=set())
        self.lock = RLock()
        self.size = 0
        self.max_size = max_size

    def _create_node(self) -> Node:
        node = Node(prev=self.usages, next=None, items=set())
        self.usages.next = node
        return node

    def _update_usage(self, item: Item):
        with self.lock:
            old_node = item.node
            new_node = item.node.next

            if new_node is None:
                new_node = self._create_node()

            old_node.items.remove(item)
            item = Item(
                node=new_node,
                key=item.key,
                value=item.value,
            )
            new_node.items.add(item)
            self.cache[item.key] = item

            if not old_node.items:
                old_node.next = None
                old_node.prev = None
                self.usages = new_node
                self.usages.prev = None

    def get(self, key: Hashable):
        item: Item = self.cache[key]
        self._update_usage(item)
        return item.value

    def set(self, key: Hashable, value: Any):
        with self.lock:
            node: Optional[Node] = self.usages

            if node is None:
                node = self._create_node()

            item = Item(node=node, key=key, value=value)
            node.items.add(item)
            self.cache[key] = item

    def __contains__(self, key) -> Any:
        if key in self.cache:
            self._update_usage(self.cache[key])
            return True
        return False
