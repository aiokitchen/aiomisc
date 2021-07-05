import typing as t
from weakref import WeakSet
from collections import Counter


class Metric:
    def __init__(self, name: str,
                 counter: t.MutableMapping[str, t.Union[float, int]],
                 default: t.Union[float, int] = 0):
        self.name: str = name
        self.counter = counter
        self.counter[name] = default

    def __get__(self) -> t.Union[float, int]:
        return self.counter[self.name]

    def __set__(self, value: t.Union[float, int]) -> None:
        self.counter[self.name] = value

    def __iadd__(self, value: t.Union[float, int]) -> "Metric":
        self.counter[self.name] += value
        return self

    def __isub__(self, value: t.Union[float, int]) -> "Metric":
        self.counter[self.name] -= value
        return self


class AbstractStatistic:
    __metrics__: t.FrozenSet[str]
    __instances__: t.MutableSet["AbstractStatistic"]
    _counter: t.MutableMapping[str, t.Union[float, int]]


CLASS_STORE: t.Set[t.Type[AbstractStatistic]] = set()


class MetaStatistic(type):
    def __new__(
        mcs, name: str,
        bases: t.Tuple[type, ...],
        dct: t.Dict[str, t.Any]
    ) -> t.Any:

        # noinspection PyTypeChecker
        klass: t.Type[AbstractStatistic] = super().__new__(
            mcs, name, bases, dct
        )   # type: ignore

        metrics = set()

        for base_class in bases:
            if not issubclass(base_class, AbstractStatistic):
                continue

            if not hasattr(base_class, '__annotations__'):
                continue

            for prop, kind in base_class.__annotations__.items():
                if kind not in (int, float):
                    continue

                if prop.startswith("_"):
                    continue

                metrics.add(prop)

        for prop, kind in klass.__annotations__.items():
            if kind not in (int, float):
                continue

            metrics.add(prop)

        klass.__metrics__ = frozenset(metrics)

        if klass.__metrics__:
            klass.__instances__ = WeakSet()
            CLASS_STORE.add(klass)

        return klass


class Statistic(AbstractStatistic, metaclass=MetaStatistic):
    def __init__(self) -> None:
        self._counter = Counter()   # type: ignore

        for prop in self.__metrics__:
            setattr(self, prop, Metric(prop, self._counter))

        self.__instances__.add(self)


# noinspection PyProtectedMember
def get_statistics(
    *kind: t.Type[Statistic]
) -> t.Generator[t.Any, t.Tuple[Statistic, str, int], None]:
    for klass in CLASS_STORE:
        if kind and not issubclass(klass, kind):
            continue

        for instance in klass.__instances__:
            for metric, value in instance._counter.items():
                yield instance, metric, value
