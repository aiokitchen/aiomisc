import logging
from abc import abstractmethod
from typing import Any, Union

from aiomisc import PeriodicCallback, Service

log = logging.getLogger(__name__)


class PeriodicService(Service):
    __required__ = ("interval",)

    interval: int | float
    delay: int | float = 0

    def __init__(self, *, name: str | None = None, **kwargs: Any):
        super().__init__(**kwargs)
        self.periodic = PeriodicCallback(self.callback, name=name)

    async def start(self) -> None:
        assert self.interval, f"Interval illegal interval {self.interval!r}"
        assert self.interval > 0, (
            f"Interval must be positive not {self.interval!r}"
        )

        self.periodic.start(self.interval, delay=self.delay, loop=self.loop)
        log.info("Periodic service %s started", self)

    async def stop(self, err: Exception | None = None) -> None:
        await self.periodic.stop(return_exceptions=True)
        log.info("Periodic service %s is stopped", self)

    @abstractmethod
    async def callback(self) -> Any:
        raise NotImplementedError

    def __str__(self) -> str:
        return f"{self.__class__.__name__}(interval={self.interval},delay={self.delay})"
