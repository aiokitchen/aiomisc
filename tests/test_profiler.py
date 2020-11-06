import asyncio
import os
from pstats import Stats
from tempfile import NamedTemporaryFile

from aiomisc.service.profiler import Profiler


async def test_profiler_start_stop():
    profiler = Profiler(interval=0.1, top_results=10)
    try:
        await profiler.start()
        await asyncio.sleep(0.5)
    finally:
        await profiler.stop()


async def test_profiler_dump():
    profiler = None
    fl = NamedTemporaryFile(delete=False)
    path = NamedTemporaryFile(delete=False).name
    fl.close()
    try:
        profiler = Profiler(
            interval=0.1, top_results=10,
            path=path,
        )
        await profiler.start()

        # Get first update
        await asyncio.sleep(0.01)
        stats1 = Stats(path)

        # Not enough sleep till next update
        await asyncio.sleep(0.01)
        stats2 = Stats(path)

        # Getting the same dump
        assert stats1.stats == stats2.stats

        # Enough sleep till next update
        await asyncio.sleep(0.2)
        stats3 = Stats(path)

        # Getting updated dump
        assert stats2.stats != stats3.stats

    finally:
        if profiler:
            await profiler.stop()
        os.remove(path)
