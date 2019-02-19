import tracemalloc
import logging
from ..periodic import PeriodicCallback
from ..service import Service
from ..thread_pool import threaded


log = logging.getLogger(__name__)


class MemoryTracer(Service):
    _tracer = None      # type: PeriodicCallback
    _log = None         # type: logging.Logger
    _snapshot_on_start = None

    logger = log.info

    interval = 5        # type: int
    top_results = 20    # type: int

    STAT_FORMAT = (
        "%(count)8s | "
        "%(count_diff)8s | "
        "%(size)8s | "
        "%(size_diff)8s | "
        "%(traceback)s\n"
    )

    async def start(self):
        tracemalloc.start()

        self._tracer = PeriodicCallback(self.show_stats)
        self._log = log.getChild(str(id(self)))

        self._snapshot_on_start = self.take_snapshot()
        self._tracer.start(self.interval)

    @staticmethod
    def humanize(num, suffix='B'):
        for unit in ('', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi'):
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    @staticmethod
    def take_snapshot() -> tracemalloc.Snapshot:
        return tracemalloc.take_snapshot()

    @staticmethod
    def compare_snapshot(snapshot_from: tracemalloc.Snapshot,
                         snapshot_to: tracemalloc.Snapshot):
        return snapshot_to.compare_to(snapshot_from, 'lineno')

    @threaded
    def show_stats(self):
        differences = self.compare_snapshot(
            self._snapshot_on_start,
            self.take_snapshot()
        )

        results = self.STAT_FORMAT % {
            "count": "Objects",
            "count_diff": "Obj.Diff",
            "size": "Memory",
            "size_diff": "Mem.Diff",
            "traceback": "Traceback"
        }
        for stat in differences[:self.top_results]:
            results += self.STAT_FORMAT % {
                "count": stat.count,
                "count_diff": stat.count_diff,
                "size": self.humanize(stat.size),
                "size_diff": self.humanize(stat.size_diff),
                "traceback": stat.traceback
            }

        self.logger("Top memory usage:\n%s", results)

    async def stop(self, exception: Exception = None):
        tracemalloc.stop()
