from collections import Counter
from typing import (
    Any, Dict, FrozenSet, Generator, MutableMapping, MutableSet, NamedTuple,
    Optional, Set, Tuple, Type, Union,
)
from weakref import WeakSet


class Metric:
    __slots__ = ("name", "counter")

    def __init__(
        self, name: str,
        counter: MutableMapping[str, Union[float, int]],
        default: Union[float, int] = 0,
    ):
        self.name: str = name
        self.counter = counter
        self.counter[name] = default

    def __get__(self) -> Union[float, int]:
        return self.counter[self.name]

    def __set__(self, value: Union[float, int]) -> None:
        self.counter[self.name] = value

    def __iadd__(self, value: Union[float, int]) -> "Metric":
        self.counter[self.name] += value
        return self

    def __isub__(self, value: Union[float, int]) -> "Metric":
        self.counter[self.name] -= value
        return self

    def __eq__(self, other: Any) -> bool:
        return self.counter[self.name] == other

    def __hash__(self) -> int:
        return hash(self.counter[self.name])


class AbstractStatistic:
    __metrics__: FrozenSet[str]
    __instances__: MutableSet["AbstractStatistic"]
    _counter: MutableMapping[str, Union[float, int]]
    name: Optional[str]


CLASS_STORE: Set[Type[AbstractStatistic]] = set()


class MetaStatistic(type):
    def __new__(
        mcs, name: str,
        bases: Tuple[type, ...],
        dct: Dict[str, Any],
    ) -> Any:

        # noinspection PyTypeChecker
        klass: Type[AbstractStatistic] = super().__new__(
            mcs, name, bases, dct,
        )   # type: ignore

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

    def __init__(self, name: Optional[str] = None) -> None:
        self._counter = Counter()   # type: ignore
        self.name = name

        for prop in self.__metrics__:
            setattr(self, prop, Metric(prop, self._counter))

        self.__instances__.add(self)


class StatisticResult(NamedTuple):
    kind: Type[AbstractStatistic]
    name: Optional[str]
    metric: str
    value: Union[int, float]


# noinspection PyProtectedMember
def get_statistics(
    *kind: Type[Statistic]
) -> Generator[Any, Tuple[Statistic, str, int], None]:
    for klass in CLASS_STORE:
        if kind and not issubclass(klass, kind):
            continue

        for instance in klass.__instances__:
            for metric, value in instance._counter.items():
                yield StatisticResult(
                    kind=klass,
                    name=instance.name,
                    metric=metric,
                    value=value,
                )
