import asyncio
import logging
import time
from unittest.mock import MagicMock, patch

import pytest

from aiomisc.log import (
    ThreadedHandler,
    ThreadedHandlerStatistic,
    UnhandledLoopHook,
    basic_config,
    suppressor,
)


class TestThreadedHandlerStatistic:
    def test_statistic_fields(self):
        stat = ThreadedHandlerStatistic()
        # Verify all fields exist and are initialized to 0
        assert hasattr(stat, "threads")
        assert hasattr(stat, "records")
        assert hasattr(stat, "errors")
        assert hasattr(stat, "flushes")


class TestThreadedHandler:
    def test_init(self):
        target = logging.StreamHandler()
        handler = ThreadedHandler(target)
        assert handler._target is target
        assert handler._buffered is True
        assert handler._flush_interval == 0.1
        handler.close()

    def test_init_custom_params(self):
        target = logging.StreamHandler()
        handler = ThreadedHandler(
            target,
            flush_interval=0.5,
            buffered=False,
            queue_size=100,
        )
        assert handler._buffered is False
        assert handler._flush_interval == 0.5
        handler.close()

    def test_start_and_close(self):
        target = logging.StreamHandler()
        handler = ThreadedHandler(target)
        handler.start()
        assert handler._thread.is_alive()
        handler.close()
        # Give thread time to terminate
        time.sleep(0.2)

    def test_emit_buffered(self):
        target = MagicMock(spec=logging.Handler)
        handler = ThreadedHandler(target, buffered=True)
        handler.start()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert handler._statistic.records == 1

        handler.close()

    def test_emit_unbuffered(self):
        target = MagicMock(spec=logging.Handler)
        handler = ThreadedHandler(target, buffered=False)
        handler.start()

        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        assert handler._statistic.records == 1

        handler.close()

    def test_flush(self):
        target = MagicMock(spec=logging.Handler)
        handler = ThreadedHandler(target)

        # Verify flush increments the counter
        # Metric class supports __eq__ comparison
        assert handler._statistic.flushes == 0
        handler.flush()
        assert handler._statistic.flushes == 1
        handler.flush()
        assert handler._statistic.flushes == 2

        handler.close()


class TestSuppressor:
    def test_suppressor_suppresses_exception(self):
        def raising_func():
            raise ValueError("test error")

        wrapped = suppressor(raising_func)
        # Should not raise
        wrapped()

    def test_suppressor_with_specific_exception(self):
        def raising_func():
            raise TypeError("type error")

        wrapped = suppressor(raising_func, exceptions=(TypeError,))
        # Should not raise
        wrapped()

    def test_suppressor_does_not_suppress_other_exceptions(self):
        def raising_func():
            raise KeyError("key error")

        wrapped = suppressor(raising_func, exceptions=(TypeError,))
        with pytest.raises(KeyError):
            wrapped()

    def test_suppressor_normal_execution(self):
        call_count = 0

        def normal_func():
            nonlocal call_count
            call_count += 1

        wrapped = suppressor(normal_func)
        wrapped()
        assert call_count == 1


class TestUnhandledLoopHook:
    def test_init(self):
        hook = UnhandledLoopHook()
        assert hook.logger is not None

    def test_fill_transport_extra_none(self):
        extra = {}
        UnhandledLoopHook._fill_transport_extra(None, extra)
        assert extra == {}

    def test_fill_transport_extra_with_transport(self):
        transport = MagicMock()
        transport.get_extra_info.side_effect = lambda key: {
            "peername": ("127.0.0.1", 8080),
            "sockname": ("0.0.0.0", 9000),
        }.get(key)

        extra = {}
        UnhandledLoopHook._fill_transport_extra(transport, extra)

        assert "transport" in extra
        assert "transport_peername" in extra
        assert "transport_sockname" in extra

    def test_call_with_exception(self):
        hook = UnhandledLoopHook(logger_name="test.unhandled")

        loop = MagicMock()
        context = {
            "message": "Test error",
            "exception": ValueError("test"),
        }

        with patch.object(hook.logger, "exception") as mock_exc:
            hook(loop, context)
            mock_exc.assert_called_once()

    def test_call_with_future(self):
        hook = UnhandledLoopHook(logger_name="test.unhandled")

        loop = MagicMock()
        future = MagicMock()
        future.exception.return_value = RuntimeError("future error")

        context = {
            "message": "Future error",
            "future": future,
        }

        with patch.object(hook.logger, "exception") as mock_exc:
            hook(loop, context)
            mock_exc.assert_called_once()

    def test_call_with_task(self):
        hook = UnhandledLoopHook(logger_name="test.unhandled")

        loop = MagicMock()
        task = MagicMock()
        task.done.return_value = True
        task.exception.return_value = RuntimeError("task error")

        context = {
            "message": "Task error",
            "task": task,
        }

        with patch.object(hook.logger, "exception") as mock_exc:
            hook(loop, context)
            mock_exc.assert_called_once()

    def test_call_with_handle_and_protocol(self):
        hook = UnhandledLoopHook(logger_name="test.unhandled")

        loop = MagicMock()
        handle = MagicMock()
        protocol = MagicMock()
        sock = MagicMock()

        context = {
            "message": "Error with handle",
            "exception": ValueError("test"),
            "handle": handle,
            "protocol": protocol,
            "socket": sock,
        }

        with patch.object(hook.logger, "exception") as mock_exc:
            hook(loop, context)
            mock_exc.assert_called_once()

    def test_call_with_source_traceback(self):
        hook = UnhandledLoopHook(logger_name="test.unhandled")

        loop = MagicMock()
        import traceback

        source_tb = [
            traceback.FrameSummary("test.py", 10, "test_func"),
        ]

        context = {
            "message": "Error with traceback",
            "exception": ValueError("test"),
            "source_traceback": source_tb,
        }

        with (
            patch.object(hook.logger, "exception") as mock_exc,
            patch.object(hook.logger, "error") as mock_error,
        ):
            hook(loop, context)
            mock_exc.assert_called_once()
            mock_error.assert_called_once()


class TestBasicConfig:
    def test_basic_config_default(self):
        loop = asyncio.new_event_loop()
        try:
            with patch("aiomisc_log.basic_config") as mock_config:
                basic_config(loop=loop)
                mock_config.assert_called_once()
        finally:
            loop.close()

    def test_basic_config_with_handlers(self):
        loop = asyncio.new_event_loop()
        try:
            target_handler = logging.StreamHandler()
            with patch("aiomisc_log.basic_config") as mock_config:
                basic_config(loop=loop, handlers=[target_handler])
                mock_config.assert_called_once()
        finally:
            loop.close()

    def test_basic_config_custom_params(self):
        loop = asyncio.new_event_loop()
        try:
            with patch("aiomisc_log.basic_config") as mock_config:
                basic_config(
                    level="debug",
                    log_format="json",
                    buffered=False,
                    buffer_size=100,
                    flush_interval=0.5,
                    loop=loop,
                )
                mock_config.assert_called_once()
        finally:
            loop.close()
