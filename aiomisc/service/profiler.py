import cProfile
import io
import logging
from pstats import Stats
from typing import Optional

from ..periodic import PeriodicCallback
from .base import Service


class Profiler(Service):
    profiler: cProfile.Profile
    periodic: PeriodicCallback

    order: str = "cumulative"

    path: Optional[str] = None
    logger: logging.Logger

    interval: int = 10
    top_results: int = 10
    log: logging.Logger = logging.getLogger(__name__)

    name: str = "profiler"

    async def start(self) -> None:
        self.logger = self.log.getChild(str(id(self)))

        self.profiler = cProfile.Profile()
        self.periodic = PeriodicCallback(self.save_stats)

        self.profiler.enable()
        self.periodic.start(self.interval)

    def save_stats(self) -> None:
        with io.StringIO() as stream:
            stats = Stats(
                self.profiler, stream=stream,
            ).strip_dirs().sort_stats(self.order)

            stats.print_stats(self.top_results)
            self.logger.info(stream.getvalue())

            try:
                if self.path is not None:
                    stats.dump_stats(self.path)
            finally:
                self.profiler.enable()

    async def stop(self, exception: Optional[Exception] = None) -> None:
        self.logger.info("Stop profiler")
        await self.periodic.stop(return_exceptions=True)
        self.profiler.disable()
