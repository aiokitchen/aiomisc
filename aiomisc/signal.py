import inspect


class Signal:

    __slots__ = ('_receivers', '_is_frozen')

    def __init__(self):
        self._receivers = []
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

        self._receivers.append(receiver)

    async def call(self, *args, **kwargs):
        for receiver in self._receivers:
            await receiver(*args, **kwargs)
