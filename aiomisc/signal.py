import inspect
from typing import Any, Callable, NamedTuple


class SignalReceiver(NamedTuple):

    callback: Callable
    expected_sender: Any


class Signal:

    __slots__ = ('_receivers', '_is_frozen')

    def __init__(self):
        self._receivers = []
        self._is_frozen = False

    def freeze(self):
        self._is_frozen = True

    def connect(self, callback, sender=None):
        if self._is_frozen:
            raise RuntimeError(
                "Can't connect callback (%r) to the frozen signal",
                callback,
            )

        if not inspect.iscoroutinefunction(callback):
            raise RuntimeError('%r is not a coroutine function', callback)

        self._receivers.append(
            SignalReceiver(callback=callback, expected_sender=sender),
        )

    async def call(self, *args, sender=None, **kwargs):
        args = args or []
        kwargs = kwargs or {}

        for receiver in self._receivers:
            if (
                receiver.expected_sender is not None
                and receiver.expected_sender != sender
            ):
                continue

            await receiver.callback(*args, sender=sender, **kwargs)
