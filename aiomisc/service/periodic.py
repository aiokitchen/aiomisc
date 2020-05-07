import logging

from aiomisc import PeriodicCallback, Service


log = logging.getLogger(__name__)


class PeriodicService(Service):

    __required__ = ("interval",)

    interval = None  # type: float # in seconds
    delay = 0  # type: float # in seconds

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.periodic = PeriodicCallback(self.callback)

    async def start(self):
        self.periodic.start(self.interval, delay=self.delay, loop=self.loop)
        log.info("Periodic service %s started", self)

    async def stop(self, err):
        if self.periodic.task:
            await self.periodic.task
        self.periodic.stop()
        log.info("Periodic service %s is stopped", self)

    async def callback(self):
        raise NotImplementedError

    def __str__(self):
        return "{}(interval={},delay={})".format(
            self.__class__.__name__,
            self.interval,
            self.delay,
        )
