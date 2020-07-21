import typing
import inspect

from .typehints import DecoratorType, T, CoroutineFunctionType

ReceiverType = typing.Callable[..., typing.Coroutine]

SignalReceiverSetType = typing.Union[
    typing.Set[ReceiverType],
    typing.FrozenSet[ReceiverType]
]


class Signal:
    __slots__ = ("_receivers", "_is_frozen")

    def __init__(self) -> None:
        self._receivers = set()  # type: SignalReceiverSetType

    def connect(self, receiver: ReceiverType) -> None:
        if self.is_frozen:
            raise RuntimeError(
                "Can't connect receiver (%r) to the frozen signal",
                receiver,
            )

        if not inspect.iscoroutinefunction(receiver):
            raise RuntimeError("%r is not a coroutine function", receiver)

        self._receivers.add(receiver)   # type: ignore

    async def call(self, *args, **kwargs) -> None:  # type: ignore
        for receiver_func in self._receivers:
            await receiver_func(*args, **kwargs)

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


def receiver(s: Signal) -> DecoratorType[CoroutineFunctionType[T]]:
    def decorator(func: CoroutineFunctionType[T]) -> CoroutineFunctionType[T]:
        s.connect(func)
        return func

    return decorator
