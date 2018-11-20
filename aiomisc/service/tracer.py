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

    interval = 5  # type: int
    top_results = 20

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

        self._snapshot_on_start = tracemalloc.take_snapshot()
        self._tracer.start(self.interval)

    @staticmethod
    def humanize(num, suffix='B'):
        for unit in ['', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi']:
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, 'Yi', suffix)

    @threaded
    def show_stats(self):
        snapshot = tracemalloc.take_snapshot()

        differences = snapshot.compare_to(self._snapshot_on_start, 'lineno')

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
