import asyncio
import os
import sys
from pstats import Stats
from tempfile import NamedTemporaryFile

import pytest

from aiomisc.service.profiler import Profiler
from tests import unix_only


async def test_profiler_start_stop():
    profiler = Profiler(interval=0.1, top_results=10)
    try:
        await profiler.start()
        await asyncio.sleep(0.5)
    finally:
        await profiler.stop()


@unix_only
@pytest.mark.skipif(
    sys.version_info < (3, 10), reason="get_stats_profile available on 3.10+"
)
async def test_profiler_dump():
    profiler = None
    fl = NamedTemporaryFile(delete=False)
    path = NamedTemporaryFile(delete=False).name
    fl.close()
    try:
        profiler = Profiler(interval=0.1, top_results=10, path=path)
        await profiler.start()

        # Get first update
        await asyncio.sleep(0.01)
        stats1 = Stats(path)

        # Not enough sleep till next update
        await asyncio.sleep(0.01)
        stats2 = Stats(path)

        # Getting the same dump
        assert stats1.get_stats_profile() == stats2.get_stats_profile()

        # Enough sleep till next update
        await asyncio.sleep(0.2)
        stats3 = Stats(path)

        # Getting updated dump
        assert stats2.get_stats_profile() != stats3.get_stats_profile()

    finally:
        if profiler:
            await profiler.stop()
        os.remove(path)
