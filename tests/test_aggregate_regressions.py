import asyncio
from typing import Any

import pytest

from aiomisc.aggregate import Arg, aggregate, aggregate_async


pytestmark = pytest.mark.catch_loop_exceptions


async def test_cancelled_waiter_does_not_break_async_batch() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @aggregate_async(60_000, max_count=2)
    async def load(*items: Arg[int, int]) -> None:
        started.set()
        await release.wait()
        for item in items:
            item.future.set_result(item.value)

    first = asyncio.create_task(load(1))
    second = asyncio.create_task(load(2))
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        # The second caller executes the full batch; cancel only its waiter.
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(first, timeout=5)
        release.set()
        assert await asyncio.wait_for(second, timeout=5) == 2
    finally:
        for task in (first, second):
            task.cancel()
        await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.parametrize("low_level", (False, True))
async def test_item_can_be_passed_by_keyword(low_level: bool) -> None:
    @aggregate(1, max_count=1)
    async def load(*items: int) -> list[int]:
        return list(items)

    @aggregate_async(1, max_count=1)
    async def load_async(*items: Arg[int, int]) -> None:
        for item in items:
            item.future.set_result(item.value)

    function = load_async if low_level else load
    assert await function(arg=42) == 42


@pytest.mark.parametrize("low_level", (False, True))
async def test_backend_keyword_named_arg(low_level: bool) -> None:
    @aggregate(1, max_count=1)
    async def load(*items: int, arg: str) -> list[tuple[int, str]]:
        return [(item, arg) for item in items]

    @aggregate_async(1, max_count=1)
    async def load_async(*items: Arg[int, tuple[int, str]], arg: str) -> None:
        for item in items:
            item.future.set_result((item.value, arg))

    function = load_async if low_level else load
    assert await function(42, arg="option") == (42, "option")


@pytest.mark.parametrize("low_level", (False, True))
async def test_method_item_and_backend_keyword(low_level: bool) -> None:
    decorator = aggregate_async if low_level else aggregate

    async def respond(values: tuple[Any, ...], arg: str) -> Any:
        return [(value, arg) for value in values]

    async def backend(*items: Any, arg: str = "default") -> Any:
        if not low_level:
            return await respond(items, arg)
        results = await respond(tuple(item.value for item in items), arg)
        for item, result in zip(items, results):
            item.future.set_result(result)

    class Loader:
        @decorator(1, max_count=1)
        async def load(self, *items: Any, arg: str = "default") -> Any:
            return await backend(*items, arg=arg)

        @decorator(1, max_count=1)
        @classmethod
        async def class_load(cls, *items: Any, arg: str = "default") -> Any:
            return await backend(*items, arg=arg)

        @classmethod
        @decorator(1, max_count=1)
        async def outer_load(cls, *items: Any, arg: str = "default") -> Any:
            return await backend(*items, arg=arg)

    loader = Loader()
    for method in (loader.load, Loader.class_load, Loader.outer_load):
        assert await method(arg=1) == (1, "default")
        assert await method(2, arg="option") == (2, "option")
    assert await Loader.load(loader, arg=3) == (3, "default")
    assert await Loader.load(loader, 4, arg="option") == (4, "option")
    with pytest.raises(TypeError, match="require an instance"):
        await Loader.load(arg=5)  # type: ignore[call-overload]
