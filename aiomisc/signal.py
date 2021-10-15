import inspect
from typing import Any, Callable, FrozenSet, Set, TypeVar, Union


T = TypeVar("T")
ReceiverType = Callable[..., Any]
_ReceiverSetType = Union[Set[ReceiverType], FrozenSet[ReceiverType]]


class Signal:

    __slots__ = ("_receivers", "_is_frozen")

    def __init__(self) -> None:
        self._receivers = set()   # type: _ReceiverSetType

    def connect(self, receiver: ReceiverType) -> None:
        if self.is_frozen:
            raise RuntimeError(
                "Can't connect receiver (%r) to the frozen signal",
                receiver,
            )

        if not inspect.iscoroutinefunction(receiver):
            raise RuntimeError("%r is not a coroutine function", receiver)

        self._receivers.add(receiver)   # type: ignore

    async def call(self, *args: Any, **kwargs: Any) -> None:
        for receiver in self._receivers:
            await receiver(*args, **kwargs)

    def copy(self) -> "Signal":
        clone = Signal()
        # unfreeze on copy
        clone._receivers = set(self._receivers)
        return clone

    @property
    def is_frozen(self) -> bool:
        return isinstance(self._receivers, frozenset)

    def freeze(self) -> None:
        self._receivers = frozenset(self._receivers)


def receiver(s: Signal) -> Callable[..., Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        s.connect(func)
        return func

    return decorator
