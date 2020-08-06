import logging

from aiomisc import Service
from aiomisc.cron import CronCallback

log = logging.getLogger(__name__)


class CronService(Service):

    __required__ = ("spec",)

    spec = None  # type: str # cron spec

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.cron = CronCallback(self.callback)

    async def start(self):
        self.cron.start(self.spec, loop=self.loop)
        log.info("Cron service %s started", self)

    async def stop(self, exception: Exception = None):
        if self.cron.task:
            await self.cron.task
        self.cron.stop()
        log.info("Cron service %s is stopped", self)

    async def callback(self):
        raise NotImplementedError

    def __str__(self):
        return "{}(spec={})".format(
            self.__class__.__name__,
            self.spec,
        )
