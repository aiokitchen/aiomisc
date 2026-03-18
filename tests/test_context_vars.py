import asyncio
from unittest.mock import MagicMock, patch

import pytest

from aiomisc.context_vars import EVENT_LOOP, StrictContextVar, set_current_loop


class TestStrictContextVar:
    def test_init(self):
        exc = RuntimeError("test error")
        var = StrictContextVar("test_var", exc)
        assert var.exc is exc
        assert var.context_var.name == "test_var"

    def test_get_raises_when_not_set(self):
        exc = ValueError("not set")
        var = StrictContextVar[int]("my_var", exc)

        with pytest.raises(ValueError, match="not set"):
            var.get()

    def test_get_returns_value_when_set(self):
        exc = RuntimeError("not set")
        var = StrictContextVar[str]("my_var", exc)

        var.set("hello")
        assert var.get() == "hello"

    def test_set_and_get_different_types(self):
        exc = RuntimeError("not set")

        # Test with int
        int_var = StrictContextVar[int]("int_var", exc)
        int_var.set(42)
        assert int_var.get() == 42

        # Test with list
        list_var = StrictContextVar[list]("list_var", exc)
        list_var.set([1, 2, 3])
        assert list_var.get() == [1, 2, 3]

        # Test with dict
        dict_var = StrictContextVar[dict]("dict_var", exc)
        dict_var.set({"key": "value"})
        assert dict_var.get() == {"key": "value"}


class TestEventLoop:
    def test_event_loop_raises_when_not_set(self):
        # Create a fresh context to ensure no loop is set
        import contextvars

        ctx = contextvars.copy_context()

        def check():
            # Reset the context var to ensure it's not set
            EVENT_LOOP.context_var.set(None)
            with pytest.raises(RuntimeError, match="no current event loop"):
                EVENT_LOOP.get()

        ctx.run(check)

    def test_event_loop_returns_loop_when_set(self):
        loop = asyncio.new_event_loop()
        try:
            EVENT_LOOP.set(loop)
            assert EVENT_LOOP.get() is loop
        finally:
            loop.close()


class TestSetCurrentLoop:
    def test_set_current_loop(self):
        loop = asyncio.new_event_loop()
        try:
            with patch("aiothreads.types.EVENT_LOOP") as mock_aiothreads_loop:
                set_current_loop(loop)

                # Verify EVENT_LOOP is set
                assert EVENT_LOOP.get() is loop

                # Verify aiothreads EVENT_LOOP.set was called
                mock_aiothreads_loop.set.assert_called_once_with(loop)
        finally:
            loop.close()
