from typing import Type, Set
from weakref import WeakSet
from collections import Counter


class AbstractStatistic:
    pass


CLASS_STORE: Set[Type[AbstractStatistic]] = set()


class MetaStatistic(type):

    def __new__(cls, name, bases, dct):
        klass = super().__new__(cls, name, bases, dct)
        klass.__metrics__ = set()

        for base_class in bases:
            if not issubclass(base_class, AbstractStatistic):
                continue

            if not hasattr(base_class, '__annotations__'):
                continue

            for prop, kind in base_class.__annotations__.items():
                if kind not in (int, float):
                    continue

                klass.__metrics__.add(prop)

        for prop, kind in klass.__annotations__.items():
            if kind not in (int, float):
                continue

            klass.__metrics__.add(prop)

        klass.__metrics__ = tuple(klass.__metrics__)

        if klass.__metrics__:
            klass.__instances__ = WeakSet()
            CLASS_STORE.add(klass)

        return klass


class Metric:
    def __init__(self, name, counter: Counter, default=0):
        self.name = name
        self.counter = counter
        self.counter[name] = default

    def __get__(self):
        return self.counter[self.name]

    def __set__(self, value):
        self.counter[self.name] = value

    def __iadd__(self, value):
        self.counter[self.name] += value
        return self

    def __isub__(self, value):
        self.counter[self.name] -= value
        return self


class Statistic(AbstractStatistic, metaclass=MetaStatistic):
    _counter: Counter

    def __init__(self):
        self._counter = Counter()

        for prop in self.__metrics__:
            setattr(self, prop, Metric(prop, self._counter))

        self.__instances__.add(self)


# noinspection PyProtectedMember
def get_statistics(*kind: Type[AbstractStatistic]):
    for klass in CLASS_STORE:
        if kind and not issubclass(klass, kind):
            continue

        for instance in klass.__instances__:
            for metric, value in instance._counter.items():
                yield instance, metric, value
