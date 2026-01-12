from collections import Counter
from collections.abc import Generator, Iterator, MutableMapping, MutableSet
from dataclasses import dataclass
from typing import Any, Union
from weakref import WeakSet


class Metric:
    __slots__ = ("counter", "name")

    def __init__(
        self,
        name: str,
        counter: MutableMapping[str, float | int],
        default: float | int = 0,
    ):
        self.name: str = name
        self.counter = counter
        self.counter[name] = default

    def __get__(self) -> float | int:
        return self.counter[self.name]

    def __set__(self, value: float | int) -> None:
        self.counter[self.name] = value

    def __iadd__(self, value: float | int) -> "Metric":
        self.counter[self.name] += value
        return self

    def __isub__(self, value: float | int) -> "Metric":
        self.counter[self.name] -= value
        return self

    def __eq__(self, other: Any) -> bool:
        return self.counter[self.name] == other

    def __hash__(self) -> int:
        return hash(self.counter[self.name])


class AbstractStatistic:
    __metrics__: frozenset[str]
    __instances__: MutableSet["AbstractStatistic"]
    _counter: MutableMapping[str, float | int]
    name: str | None


CLASS_STORE: set[type[AbstractStatistic]] = set()


class MetaStatistic(type):
    def __new__(
        mcs, name: str, bases: tuple[type, ...], dct: dict[str, Any]
    ) -> Any:
        # noinspection PyTypeChecker
        klass: type[AbstractStatistic] = super().__new__(  # type: ignore
            mcs, name, bases, dct
        )

        metrics = set()

        for base_class in bases:
            if not issubclass(base_class, AbstractStatistic):
                continue

            if not hasattr(base_class, "__annotations__"):
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
    __slots__ = ("_counter", "name")

    def __init__(self, name: str | None = None) -> None:
        self._counter = Counter()  # type: ignore
        self.name = name

        for prop in self.__metrics__:
            setattr(self, prop, Metric(prop, self._counter))

        self.__instances__.add(self)


@dataclass(frozen=True)
class StatisticResult:
    kind: type[AbstractStatistic]
    name: str | None
    metric: str
    value: int | float

    def __iter__(self) -> Iterator:
        yield self.kind
        yield self.name
        yield self.metric
        yield self.value


# noinspection PyProtectedMember
def get_statistics(
    *kind: type[Statistic],
) -> Generator[Any, tuple[Statistic, str, int], None]:
    for klass in CLASS_STORE:
        if kind and not issubclass(klass, kind):
            continue

        for instance in klass.__instances__:
            for metric, value in instance._counter.items():
                yield StatisticResult(
                    kind=klass, name=instance.name, metric=metric, value=value
                )
