import asyncio
import logging
from asyncio import iscoroutinefunction
from typing import Any, Callable, NamedTuple, Set, Tuple, Type

from croniter import croniter

from aiomisc import Service
from aiomisc.cron import CronCallback


log = logging.getLogger(__name__)
ExceptionsType = Tuple[Type[Exception], ...]


class StoreItem(NamedTuple):
    callback: CronCallback
    spec: str
    shield: bool
    suppress_exceptions: ExceptionsType


class CronService(Service):
    _callbacks_storage: Set[StoreItem]

    def __init__(self, **kwargs: Any):
        super(CronService, self).__init__(**kwargs)
        self._callbacks_storage = set()

    def register(
        self,
        function: Callable,
        spec: str,
        shield: bool = False,
        suppress_exceptions: ExceptionsType = (),
    ) -> None:
        if not iscoroutinefunction(function):
            raise TypeError("function should be a coroutine %r" % function)
        if not croniter.is_valid(spec):
            raise TypeError("Not valid cron spec %r" % spec)

        self._callbacks_storage.add(
            StoreItem(
                CronCallback(function), spec, shield, suppress_exceptions,
            ),
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

    async def stop(self, exception: Exception = None) -> None:
        async def _shutdown(item: StoreItem) -> None:
            if item.callback.task:
                await item.callback.task
            # noinspection PyAsyncCall
            item.callback.stop()

        await asyncio.gather(
            *[_shutdown(store) for store in self._callbacks_storage],
            return_exceptions=True,
        )
        log.info("Cron service %s is stopped", self)

    def __str__(self) -> str:
        storage = ", ".join(
            "{}: {}".format(item.callback, item.spec) for item in
            self._callbacks_storage
        )
        return "{}({})".format(
            self.__class__.__name__,
            storage,
        )
