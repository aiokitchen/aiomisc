import cProfile
import io
import logging
from asyncio import CancelledError
from contextlib import suppress
from pstats import Stats

from ..periodic import PeriodicCallback
from .base import Service


class Profiler(Service):
    profiler = None        # type: cProfile.Profile
    periodic = None        # type: PeriodicCallback

    order = "cumulative"    # type: str

    path = None             # type: str
    logger = None           # type: logging.Logger

    interval = 10           # type: int
    top_results = 10        # type: int
    log = logging.getLogger(__name__)   # type: logging.Logger

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

    async def stop(self, exception: Exception = None) -> None:
        self.logger.info("Stop profiler")

        task = self.periodic.stop()
        with suppress(CancelledError):
            await task

        self.profiler.disable()
