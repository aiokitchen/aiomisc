from typing import Any, Dict, Generic, Hashable, List, Optional, Tuple, TypeVar


K = Tuple[str, ...]
T = TypeVar("T", bound=Any)


class RadixNode(Generic[T]):
    __slots__ = ("children", "value")

    def __init__(self) -> None:
        self.children: Dict[Hashable, RadixNode[T]] = {}
        self.value: Optional[T] = None


class RadixTree(Generic[T]):
    root: RadixNode[T]

    __slots__ = ("root",)

    def __init__(self) -> None:
        self.root = RadixNode()

    def insert(self, key: K, value: Optional[T]) -> None:
        node = self.root
        for part in key:
            if part not in node.children:
                node.children[part] = RadixNode()
            node = node.children[part]
        node.value = value

    def search(self, key: K) -> Optional[T]:
        node = self.root
        for part in key:
            if part not in node.children:
                return None
            node = node.children[part]
        return node.value

    def find_prefix(self, key: K) -> Optional[Tuple[K, T]]:
        node = self.root
        longest_prefix: List[str] = []
        value = None
        part: Hashable
        if node.value is not None:
            value = node.value
        for part in key:
            if part in node.children:
                node = node.children[part]
                longest_prefix.append(part)
                if node.value is not None:
                    value = node.value
            else:
                break

        if value is None:
            return None

        return tuple(longest_prefix), value
