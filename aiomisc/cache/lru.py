from threading import RLock
from typing import Any, Hashable, Dict, Optional
from aiomisc.cache.base import CacheBase


# noinspection PyShadowingBuiltins
class Node:
    __slots__ = 'prev', 'next', 'item', '_restricted'

    def __init__(self, prev: "Node" = None, next: "Node" = None,
                 item: Optional["Item"] = None):
        self.prev = prev
        self.next = next
        self.item = item


class Item:
    __slots__ = 'node', 'key', 'value', '_restricted'

    def __init__(self, node: Node, key: Hashable, value: Any):
        self.node: Node = node
        self.key: Hashable = key
        self.value: Any = value


class LRUCache(CacheBase):
    """
        LRU cache implementation

        >>> lfu = LRUCache(3)
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
        >>> assert len(lfu) == 3, str(len(lfu)) + " is not 3"
    """

    __slots__ = 'lock', 'cache', 'last', 'first'

    def __init__(self, max_size: int):
        super().__init__(max_size)
        self.cache: Dict[Hashable, Item] = dict()
        self.first: Optional[Node] = None
        self.last: Optional[Node] = None
        self.lock: RLock = RLock()

    @staticmethod
    def _node_remove(node: Node):
        if node.next is None:
            return

        node.prev.next = node.next
        node.prev = None
        node.next = None

    @staticmethod
    def _node_append_left(parent: Node, node: Node):
        """
        Appends node before the parent node

        before:

            ... <-> [parent] <-> ...

        after:

            ... <-> [node] <-> [parent] <-> ...

        """
        node.next = parent

        if parent.prev is not None:
            node.prev = parent.prev

        parent.prev = node

    @staticmethod
    def _node_append_right(parent: Node, node: Node):
        """
        Appends node after parent node

        before:

            ... <-> [parent] <-> ...

        after:

            ... <-> [parent] <-> [node] <-> ...

        """
        node.prev = parent

        if parent.next is not None:
            node.next = parent.next

        parent.next = node

    @staticmethod
    def _node_swap(a: Node, b: Node):
        """
        Swaps two Nodes and change neighbor links

        Example: doubly linked list looks like:

              [x]  <->  [a]  <->  [z]  <->  [b]  <->  [y]
            node x    node a    node z    node b    node y
            p    n    p    n    p    n    p    n    p    n
            ----------------------------------------------
            -    a    x    z    a    b    z    y    b    -

        After swap should looks like:

              [x]  <->  [b]  <->  [z]  <->  [a]  <->  [y]
            node x    node b    node z    node a    node y
            p    n    p    n    p    n    p    n    p    n
            ----------------------------------------------
            -    b    x    z    b    a    z    y    a    -

        That's means we should make 8 changes

            # 4 for "a" and "b"
            a.prev, a.next, b.prev, b.next = b.prev, b.next, a.prev, a.next

            # 4 for neighbors
            x.next, z.prev, z.next, y.prev = b, b, a, a

        After general case is should be:

            a.prev.next, a.next.prev, b.prev.next, b.next.prev = b, b, a, a
            a.prev, a.next, b.prev, b.next = b.prev, b.next, a.prev, a.next

        """
        # store original links
        a_prev, a_next, b_prev, b_next = a.prev, a.next, b.prev, b.next

        if a_prev is not None:
            a_prev.next = b
            a.prev = b_prev

        if a_next is not None:
            a_next.prev = b
            a.next = b_next

        if b_next is not None:
            b_next.prev = a
            b.next = b_next

        if b_prev is not None:
            b_prev.next = a
            b.prev = a_prev

    def _on_overflow(self):
        with self.lock:
            while self._is_overflow():
                node = self.first
                if self.first is None:
                    return

                self.first = self.first.next
                self.remove(node.item.key)

                if self.first is None:
                    self.first = Node(prev=None, next=None)

    def _is_overflow(self) -> bool:
        return len(self.cache) > self.max_size

    def get(self, key: Hashable):
        item = self.cache[key]

        with self.lock:
            self._node_swap(item.node, self.last)

        return item.value

    def remove(self, key: Hashable):
        with self.lock:
            item: Optional[Item] = self.cache.pop(key, None)
            if item is None:
                return
            self._node_remove(item.node)

    def set(self, key: Hashable, value: Any):
        with self.lock:
            node = Node(prev=self.last)
            item = Item(node=node, key=key, value=value)
            node.item = item
            self.cache[key] = item

            if self.last is None and self.first is None:
                self.last = self.first = node
                return

            self._node_append_right(self.last, node)
            self.last = node

        if self._is_overflow():
            self._on_overflow()

    def __contains__(self, key: Hashable):
        return key in self.cache

    def __len__(self):
        return len(self.cache)
