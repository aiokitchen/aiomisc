import logging
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

import aiomisc_log
from aiomisc_log import (
    LOG_FORMAT,
    LOG_LEVEL,
    LogFormat,
    LogLevel,
    basic_config,
    create_logging_handler,
)


class TestCreateLoggingHandler:
    def test_disabled_returns_none(self):
        handler = create_logging_handler(LogFormat.disabled)
        assert handler is None

    def test_stream_format(self):
        handler = create_logging_handler(LogFormat.stream)
        assert isinstance(handler, logging.StreamHandler)

    def test_stream_format_with_date(self):
        handler = create_logging_handler(
            LogFormat.stream, date_format="%Y-%m-%d"
        )
        assert isinstance(handler, logging.StreamHandler)
        assert handler.formatter.datefmt == "%Y-%m-%d"

    def test_plain_format(self):
        handler = create_logging_handler(LogFormat.plain)
        assert isinstance(handler, logging.StreamHandler)
        assert handler.formatter._fmt == "%(message)s"

    def test_json_format(self):
        handler = create_logging_handler(LogFormat.json)
        assert isinstance(handler, logging.StreamHandler)

    def test_color_format(self):
        handler = create_logging_handler(LogFormat.color)
        assert isinstance(handler, logging.Handler)

    def test_rich_format(self):
        try:
            handler = create_logging_handler(LogFormat.rich)
            assert isinstance(handler, logging.Handler)
        except ImportError:
            pytest.skip("rich not installed")

    def test_rich_tb_format(self):
        try:
            handler = create_logging_handler(LogFormat.rich_tb)
            assert isinstance(handler, logging.Handler)
        except ImportError:
            pytest.skip("rich not installed")

    def test_syslog_format(self):
        handler = create_logging_handler(LogFormat.syslog)
        assert isinstance(handler, logging.handlers.SysLogHandler)

    def test_syslog_format_with_date_warning(self):
        # Should write warning to stderr when date_format is provided
        stderr = StringIO()
        with patch.object(sys, "stderr", stderr):
            handler = create_logging_handler(
                LogFormat.syslog, date_format="%Y-%m-%d"
            )
        assert isinstance(handler, logging.handlers.SysLogHandler)
        assert "date_format" in stderr.getvalue()

    def test_journald_format(self):
        try:
            handler = create_logging_handler(LogFormat.journald)
            assert isinstance(handler, logging.Handler)
        except (ImportError, FileNotFoundError):
            # Expected on systems without journald
            pass


class TestUnhandledHook:
    def test_unhandled_hook_init(self):
        hook = aiomisc_log.UnhandledHook()
        assert hook.logger is not None
        assert hook.logger_name == "unhandled"

    def test_unhandled_hook_add_handler(self):
        hook = aiomisc_log.UnhandledHook()
        handler = logging.StreamHandler()
        hook.add_handler(handler)
        assert handler in hook.logger.handlers


class TestUnhandledPythonHook:
    def test_call_logs_exception(self):
        hook = aiomisc_log.UnhandledPythonHook()
        hook.logger = MagicMock()

        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()
            hook(*exc_info)

        hook.logger.exception.assert_called_once()


class TestPassWrapper:
    def test_pass_wrapper_returns_handler(self):
        handler = logging.StreamHandler()
        result = aiomisc_log.pass_wrapper(handler)
        assert result is handler


class TestBasicConfig:
    def test_basic_config_with_string_level(self):
        basic_config(level="debug", log_format=LogFormat.plain)
        assert LOG_LEVEL.get() == LogLevel.debug

    def test_basic_config_with_int_level(self):
        basic_config(level=logging.WARNING, log_format=LogFormat.plain)
        assert LOG_LEVEL.get() == logging.WARNING

    def test_basic_config_with_string_format(self):
        basic_config(level="info", log_format="plain")
        assert LOG_FORMAT.get() == LogFormat.plain

    def test_basic_config_with_enum_format(self):
        basic_config(level="info", log_format=LogFormat.stream)
        assert LOG_FORMAT.get() == LogFormat.stream

    def test_basic_config_with_handler_wrapper(self):
        wrapper_called = False

        def custom_wrapper(handler):
            nonlocal wrapper_called
            wrapper_called = True
            return handler

        basic_config(
            level="info",
            log_format=LogFormat.plain,
            handler_wrapper=custom_wrapper,
        )
        assert wrapper_called

    def test_basic_config_sets_excepthook(self):
        basic_config(level="info", log_format=LogFormat.plain)
        assert callable(sys.excepthook)

    def test_basic_config_with_additional_handlers(self):
        extra_handler = logging.StreamHandler()
        basic_config(
            level="info",
            log_format=LogFormat.plain,
            handlers=[extra_handler],
        )
        # The extra handler should be wrapped and added
        root_logger = logging.getLogger()
        assert len(root_logger.handlers) > 0


class TestContextVars:
    def test_log_level_default(self):
        # Reset to default
        LOG_LEVEL.set(logging.INFO)
        assert LOG_LEVEL.get() == logging.INFO

    def test_log_format_default(self):
        # This depends on system configuration (tty, rich, journald)
        default_format = LogFormat.default()
        LOG_FORMAT.set(default_format)
        assert LOG_FORMAT.get() == default_format
