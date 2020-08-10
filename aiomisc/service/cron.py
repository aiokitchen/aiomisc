import asyncio
import logging
from asyncio import iscoroutinefunction
from collections import namedtuple
from typing import Callable, Tuple, Type

from croniter import croniter

from aiomisc import Service
from aiomisc.cron import CronCallback

log = logging.getLogger(__name__)

StoreItem = namedtuple(
    "StoreItem", "callback, spec, shield, suppress_exceptions"
)


class CronService(Service):
    def __init__(self, **kwargs):
        super(CronService, self).__init__(**kwargs)
        self._callbacks_storage = set()

    def register(
            self,
            function: Callable,
            spec: str,
            shield: bool = False,
            suppress_exceptions: Tuple[Type[Exception]] = ()
    ):
        if not iscoroutinefunction(function):
            raise TypeError("function should be a coroutine %r" % function)
        if not croniter.is_valid(spec):
            raise TypeError("Not valid cron spec %r" % spec)

        self._callbacks_storage.add(
            StoreItem(CronCallback(function), spec, shield, suppress_exceptions)
        )

    async def start(self):
        for item in self._callbacks_storage:
            item.callback.start(
                spec=item.spec,
                loop=self.loop,
                shield=item.shield,
                suppress_exceptions=item.suppress_exceptions
            )
        log.info("Cron service %s started", self)

    async def stop(self, exception: Exception = None):
        async def _shutdown(item: StoreItem):
            if item.callback.task:
                await item.callback.task
            item.callback.stop()

        await asyncio.gather(
            *[_shutdown(store) for store in self._callbacks_storage],
            return_exceptions=True,
        )
        log.info("Cron service %s is stopped", self)

    def __str__(self):
        storage = ", ".join(
            "{}: {}".format(item.callback, item.spec) for item in
            self._callbacks_storage
        )
        return "{}({})".format(
            self.__class__.__name__,
            storage,
        )
