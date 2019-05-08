from asyncio import CancelledError
from contextlib import suppress
import cProfile
import io
import logging
from pstats import Stats

from .base import Service
from ..periodic import PeriodicCallback

log = logging.getLogger(__name__)


class Profiler(Service):
    _profiler: cProfile.Profile = None
    _periodic: PeriodicCallback = None
    _log = None

    path = None
    order = 'cumulative'

    logger = log.info

    interval: int = 10
    top_results: int = 10

    i = 0

    async def start(self):
        log.info("Start profiler")

        self._profiler = cProfile.Profile()
        self._periodic = PeriodicCallback(self.save_stats)
        self._log = log.getChild(str(id(self)))

        self._profiler.enable()
        self._periodic.start(self.interval)

    def save_stats(self):
        stream = io.StringIO()
        stats = Stats(
            self._profiler, stream=stream
        ).strip_dirs().sort_stats(self.order)
        stats.print_stats(self.top_results)
        log.info(stream.getvalue())
        stream.close()
        try:
            if self.path is not None:
                stats.dump_stats(self.path)
        finally:
            self._profiler.enable()

    async def stop(self, exception: Exception = None):
        log.info("Stop profiler")

        task = self._periodic.stop()
        with suppress(CancelledError):
            await task

        self._profiler.disable()
