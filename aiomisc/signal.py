import inspect


class Signal:

    __slots__ = ('_receivers', '_is_frozen')

    def __init__(self):
        self._receivers = set()

    def connect(self, receiver):
        if self.is_frozen:
            raise RuntimeError(
                "Can't connect receiver (%r) to the frozen signal",
                receiver,
            )

        if not inspect.iscoroutinefunction(receiver):
            raise RuntimeError('%r is not a coroutine function', receiver)

        self._receivers.add(receiver)

    async def call(self, *args, **kwargs):
        for receiver in self._receivers:
            await receiver(*args, **kwargs)

    def copy(self):
        clone = Signal()
        # unfreeze on copy
        clone._receivers = set(self._receivers)
        return clone

    @property
    def is_frozen(self):
        return isinstance(self._receivers, frozenset)

    def freeze(self):
        self._receivers = frozenset(self._receivers)


def receiver(s: Signal):
    def decorator(func):
        s.connect(func)
        return func

    return decorator
