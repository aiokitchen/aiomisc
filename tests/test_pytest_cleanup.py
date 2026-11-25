import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from aiomisc.pytest import _cancel_pending_tasks
import aiomisc.pytest as plugin


@pytest.mark.parametrize("raise_on_cancel", (False, True))
def test_cancel_pending_tasks(raise_on_cancel):
    loop = asyncio.new_event_loop()
    errors = []
    loop.set_exception_handler(lambda _, context: errors.append(context))

    async def pending():
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            if raise_on_cancel:
                raise ValueError("cleanup failed")
            raise

    try:
        task = loop.create_task(pending())
        loop.run_until_complete(asyncio.sleep(0))
        _cancel_pending_tasks(loop)

        assert not asyncio.all_tasks(loop)
        if raise_on_cancel:
            assert len(errors) == 1
            assert isinstance(errors[0]["exception"], ValueError)
            assert errors[0]["task"] is task
        else:
            assert task.cancelled()
            assert not errors
    finally:
        loop.close()


@pytest.mark.parametrize("during_cleanup", (False, True))
def test_fixture_closes_loop_before_reporting_errors(
    monkeypatch, caplog, during_cleanup
):
    loop = asyncio.new_event_loop()
    previous_loop = asyncio.get_event_loop()
    real_set_event_loop = asyncio.set_event_loop
    set_event_loop = Mock(wraps=real_set_event_loop)
    monkeypatch.setattr(plugin, "_create_event_loop", lambda: loop)
    monkeypatch.setattr(plugin, "basic_config", Mock())
    monkeypatch.setattr(plugin, "set_current_loop", Mock())
    monkeypatch.setattr(
        plugin, "mock_get_event_loop", lambda: nullcontext(Mock())
    )
    monkeypatch.setattr(asyncio, "set_event_loop", set_event_loop)
    request = SimpleNamespace(
        node=SimpleNamespace(
            get_closest_marker=lambda name: name == "catch_loop_exceptions"
        )
    )
    fixture = plugin.event_loop.__wrapped__(  # type: ignore[attr-defined]
        request, caplog, 1, False, ThreadPoolExecutor
    )
    assert next(fixture) is loop
    if during_cleanup:

        async def pending():
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                raise ValueError("cleanup failed") from None

        loop.create_task(pending())
        loop.run_until_complete(asyncio.sleep(0))
    else:
        loop.call_exception_handler(
            {"message": "test error", "exception": ValueError("test error")}
        )
    with pytest.raises(pytest.fail.Exception, match="Unhandled exceptions"):
        next(fixture)
    assert loop.is_closed()
    set_event_loop.assert_called_with(None)
    real_set_event_loop(previous_loop)
