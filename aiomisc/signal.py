import inspect


class Signal:

    __slots__ = ('_receivers', '_is_frozen')

    def __init__(self):
        self._receivers = set()
        self._is_frozen = False

    def freeze(self):
        self._is_frozen = True

    def connect(self, receiver):
        if self._is_frozen:
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
        clone._receivers = self._receivers.copy()
        clone._is_frozen = self._is_frozen
        return clone


def receiver(s: Signal):
    def decorator(func):
        s.connect(func)
        return func

    return decorator
