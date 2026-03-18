import tracemalloc
from unittest.mock import MagicMock, patch

import pytest

from aiomisc.service.tracer import GroupBy, MemoryTracer


pytestmark = pytest.mark.catch_loop_exceptions


class TestGroupBy:
    def test_groupby_values(self):
        assert GroupBy.lineno.value == "lineno"
        assert GroupBy.filename.value == "filename"
        assert GroupBy.traceback.value == "traceback"


class TestMemoryTracer:
    def test_init_defaults(self):
        tracer = MemoryTracer()
        assert tracer.interval == 5
        assert tracer.top_results == 20
        assert tracer.group_by == GroupBy.lineno
        assert tracer.name == "memory-tracer"

    def test_humanize(self):
        assert MemoryTracer.humanize(512) == "512.0B"
        assert MemoryTracer.humanize(1024) == "1.0KiB"
        assert MemoryTracer.humanize(1024 * 1024) == "1.0MiB"
        assert MemoryTracer.humanize(1024 * 1024 * 1024) == "1.0GiB"
        assert MemoryTracer.humanize(1024 * 1024 * 1024 * 1024) == "1.0TiB"

    def test_humanize_fractional(self):
        assert MemoryTracer.humanize(1536) == "1.5KiB"
        assert MemoryTracer.humanize(2560) == "2.5KiB"

    def test_take_snapshot(self):
        tracemalloc.start()
        try:
            snapshot = MemoryTracer.take_snapshot()
            assert isinstance(snapshot, tracemalloc.Snapshot)
        finally:
            tracemalloc.stop()

    def test_compare_snapshot(self):
        tracemalloc.start()
        try:
            tracer = MemoryTracer()
            snap1 = MemoryTracer.take_snapshot()

            # Allocate some memory
            _ = [i for i in range(10000)]

            snap2 = MemoryTracer.take_snapshot()
            diff = tracer.compare_snapshot(snap1, snap2)

            assert isinstance(diff, list)
        finally:
            tracemalloc.stop()

    def test_log_diff(self):
        tracemalloc.start()
        try:
            tracer = MemoryTracer()
            tracer.logger = MagicMock()  # type: ignore[method-assign]

            snap1 = MemoryTracer.take_snapshot()
            _ = [i for i in range(10000)]
            snap2 = MemoryTracer.take_snapshot()

            diff = tracer.compare_snapshot(snap1, snap2)
            tracer.log_diff(diff)

            tracer.logger.assert_called_once()
        finally:
            tracemalloc.stop()

    async def test_start_and_stop(self, event_loop):
        tracer = MemoryTracer()
        tracer.interval = 1

        await tracer.start()

        assert tracemalloc.is_tracing()
        assert tracer._tracer is not None
        assert tracer._snapshot_on_start is not None

        await tracer.stop()

        assert not tracemalloc.is_tracing()

    async def test_show_stats(self, event_loop):
        tracer = MemoryTracer()
        tracer.logger = MagicMock()  # type: ignore[method-assign]

        await tracer.start()

        # Call show_stats directly
        await tracer.show_stats()

        tracer.logger.assert_called()

        await tracer.stop()

    async def test_custom_group_by(self, event_loop):
        tracer = MemoryTracer()
        tracer.group_by = GroupBy.filename
        tracer.logger = MagicMock()  # type: ignore[method-assign]

        await tracer.start()
        await tracer.show_stats()
        await tracer.stop()

        tracer.logger.assert_called()

    async def test_custom_top_results(self, event_loop):
        tracer = MemoryTracer()
        tracer.top_results = 5
        tracer.logger = MagicMock()  # type: ignore[method-assign]

        await tracer.start()
        await tracer.show_stats()
        await tracer.stop()

        tracer.logger.assert_called()

    def test_stat_format(self):
        expected_keys = [
            "%(count)",
            "%(count_diff)",
            "%(size)",
            "%(size_diff)",
            "%(traceback)",
        ]
        for key in expected_keys:
            assert key in MemoryTracer.STAT_FORMAT
