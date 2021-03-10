from abc import ABC, abstractmethod
from typing import Any, Hashable


class CacheBase(ABC):
    __slots__ = "max_size",

    def __init__(self, max_size: int = 0):
        self.max_size = max_size

    @abstractmethod
    def get(self, key: Hashable):
        raise NotImplementedError

    @abstractmethod
    def remove(self, key: Hashable):
        raise NotImplementedError

    @abstractmethod
    def set(self, key: Hashable, value: Any):
        raise NotImplementedError

    @abstractmethod
    def __contains__(self, key: Hashable):
        raise NotImplementedError

    @abstractmethod
    def __len__(self):
        raise NotImplementedError
