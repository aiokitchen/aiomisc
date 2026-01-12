import asyncio
import logging
from asyncio import iscoroutinefunction
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from croniter import croniter

from aiomisc import Service
from aiomisc.cron import CronCallback

log = logging.getLogger(__name__)
ExceptionsType = tuple[type[Exception], ...]


@dataclass(frozen=True)
class StoreItem:
    callback: CronCallback
    spec: str
    shield: bool
    suppress_exceptions: ExceptionsType


class CronService(Service):
    _callbacks_storage: set[StoreItem]

    def __init__(self, **kwargs: Any):
        super().__init__(**kwargs)
        self._callbacks_storage = set()

    def register(
        self,
        function: Callable,
        spec: str,
        shield: bool = False,
        suppress_exceptions: ExceptionsType = (),
    ) -> None:
        if not iscoroutinefunction(function):
            raise TypeError(f"function should be a coroutine {function!r}")
        if not croniter.is_valid(spec):
            raise TypeError(f"Not valid cron spec {spec!r}")

        self._callbacks_storage.add(
            StoreItem(CronCallback(function), spec, shield, suppress_exceptions)
        )

    async def start(self) -> None:
        for item in self._callbacks_storage:
            item.callback.start(
                spec=item.spec,
                loop=self.loop,
                shield=item.shield,
                suppress_exceptions=item.suppress_exceptions,
            )
        log.info("Cron service %s started", self)

    async def stop(self, exception: Exception | None = None) -> None:
        async def _shutdown(item: StoreItem) -> None:
            await asyncio.gather(item.callback.stop(), return_exceptions=True)

        await asyncio.gather(
            *[_shutdown(store) for store in self._callbacks_storage],
            return_exceptions=True,
        )
        log.info("Cron service %s is stopped", self)
