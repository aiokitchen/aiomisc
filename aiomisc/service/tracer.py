import logging
import tracemalloc
from enum import Enum
from typing import Any, List, Union

from ..periodic import PeriodicCallback
from ..service import Service
from ..thread_pool import threaded


log = logging.getLogger(__name__)


class GroupBy(Enum):
    lineno = "lineno"
    filename = "filename"
    traceback = "traceback"


class MemoryTracer(Service):
    _tracer: PeriodicCallback
    _log: logging.Logger
    _snapshot_on_start: tracemalloc.Snapshot

    logger = log.info

    interval: int = 5
    top_results: int = 20

    group_by: GroupBy = GroupBy.lineno

    STAT_FORMAT: str = (
        "%(count)8s | "
        "%(count_diff)8s | "
        "%(size)8s | "
        "%(size_diff)8s | "
        "%(traceback)s\n"
    )

    async def start(self) -> None:
        log.warning("Start memory tracer")
        tracemalloc.start()

        self._tracer = PeriodicCallback(self.show_stats)
        self._log = log.getChild(str(id(self)))

        self._snapshot_on_start = self.take_snapshot()
        self._tracer.start(self.interval)

    @staticmethod
    def humanize(num: Union[int, float], suffix: str = "B") -> str:
        for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
            if abs(num) < 1024.0:
                return "%3.1f%s%s" % (num, unit, suffix)
            num /= 1024.0
        return "%.1f%s%s" % (num, "Yi", suffix)

    @staticmethod
    def take_snapshot() -> tracemalloc.Snapshot:
        return tracemalloc.take_snapshot()

    def compare_snapshot(
        self, snapshot_from: tracemalloc.Snapshot,
        snapshot_to: tracemalloc.Snapshot,
    ) -> List[tracemalloc.StatisticDiff]:
        return snapshot_to.compare_to(snapshot_from, self.group_by.value)

    def log_diff(self, diff: List[tracemalloc.StatisticDiff]) -> None:
        results = self.STAT_FORMAT % {
            "count": "Objects",
            "count_diff": "Obj.Diff",
            "size": "Memory",
            "size_diff": "Mem.Diff",
            "traceback": "Traceback",
        }
        for stat in diff[:self.top_results]:
            results += self.STAT_FORMAT % {
                "count": stat.count,
                "count_diff": stat.count_diff,
                "size": self.humanize(stat.size),
                "size_diff": self.humanize(stat.size_diff),
                "traceback": stat.traceback,
            }

        self.logger("Top memory usage:\n%s", results)

    @threaded
    def show_stats(self) -> Any:
        if self._snapshot_on_start is None:
            raise RuntimeError

        differences = self.compare_snapshot(
            self._snapshot_on_start,
            self.take_snapshot(),
        )

        return self.log_diff(differences)

    async def stop(self, exception: Exception = None) -> None:
        tracemalloc.stop()
