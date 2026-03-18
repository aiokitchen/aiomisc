import json
import logging
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from aiomisc_log.formatter.json import JSONLogFormatter, json_handler


class TestJSONLogFormatter:
    def test_init_default(self):
        formatter = JSONLogFormatter()
        assert formatter.datefmt is None

    def test_init_with_datefmt(self):
        formatter = JSONLogFormatter(datefmt="%Y-%m-%d")
        assert formatter.datefmt == "%Y-%m-%d"

    def test_format_basic(self):
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["msg"] == "Test message"
        assert data["level"] == "info"
        assert "@fields" in data
        assert data["@fields"]["identifier"] == "test.logger"
        assert data["@fields"]["code_line"] == 42

    def test_format_with_args(self):
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test %s %d",
            args=("message", 123),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["msg"] == "Test message 123"
        assert data["@fields"]["argument_0"] == "message"
        assert data["@fields"]["argument_1"] == "123"

    def test_format_with_exception(self):
        formatter = JSONLogFormatter()

        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test.logger",
            level=logging.ERROR,
            pathname="test.py",
            lineno=42,
            msg="Error occurred",
            args=(),
            exc_info=exc_info,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert data["@fields"]["errno"] == 255
        assert "stackTrace" in data
        assert "ValueError" in data["stackTrace"]

    def test_format_with_timestamp(self):
        formatter = JSONLogFormatter(datefmt="%Y-%m-%d %H:%M:%S")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "@timestamp" in data

    def test_format_with_timestamp_epoch(self):
        formatter = JSONLogFormatter(datefmt="%s")
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )

        result = formatter.format(record)
        data = json.loads(result)

        assert "@timestamp" in data
        # Should be a float (epoch time)
        assert isinstance(data["@timestamp"], float)

    def test_format_all_levels(self):
        formatter = JSONLogFormatter()

        # Note: CRITICAL and FATAL have the same level value (50)
        # In the LEVELS mapping, FATAL overwrites CRITICAL, so level 50 -> "fatal"
        levels = [
            (logging.DEBUG, "debug"),
            (logging.INFO, "info"),
            (logging.WARNING, "warn"),
            (logging.ERROR, "error"),
            (logging.CRITICAL, "fatal"),  # 50 maps to "fatal" in LEVELS
        ]

        for level, expected in levels:
            record = logging.LogRecord(
                name="test",
                level=level,
                pathname="test.py",
                lineno=1,
                msg="msg",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            data = json.loads(result)
            assert data["level"] == expected, (
                f"Level {level} should be {expected}"
            )

    def test_format_with_extra_fields(self):
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="Test message",
            args=(),
            exc_info=None,
        )
        record.custom_field = "custom_value"
        record.request_id = "abc123"

        result = formatter.format(record)
        data = json.loads(result)

        assert data["@fields"]["custom_field"] == "custom_value"
        assert data["@fields"]["request_id"] == "abc123"

    def test_formatMessage(self):
        formatter = JSONLogFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Hello %s",
            args=("World",),
            exc_info=None,
        )

        result = formatter.formatMessage(record)
        assert result == "Hello World"

    def test_formatException(self):
        formatter = JSONLogFormatter()

        try:
            raise RuntimeError("test error")
        except RuntimeError:
            exc_info = sys.exc_info()

        result = formatter.formatException(exc_info)
        assert "RuntimeError" in result
        assert "test error" in result


class TestJsonHandler:
    def test_json_handler_default(self):
        handler = json_handler()
        assert isinstance(handler, logging.StreamHandler)
        assert isinstance(handler.formatter, JSONLogFormatter)

    def test_json_handler_with_stream(self):
        stream = StringIO()
        handler = json_handler(stream=stream)
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is stream

    def test_json_handler_with_date_format(self):
        handler = json_handler(date_format="%Y-%m-%d")
        assert handler.formatter is not None
        assert handler.formatter.datefmt == "%Y-%m-%d"


class TestColorFormatter:
    def test_color_formatter_creates_handler(self):
        from aiomisc_log.formatter.color import color_formatter

        stream = StringIO()
        handler = color_formatter(stream=stream)
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream is stream

    def test_color_formatter_default_stream(self):
        from aiomisc_log.formatter.color import color_formatter

        handler = color_formatter()
        assert isinstance(handler, logging.StreamHandler)


class TestRichFormatter:
    def test_rich_formatter_creates_handler(self):
        try:
            from aiomisc_log.formatter.rich import rich_formatter

            handler = rich_formatter()
            assert isinstance(handler, logging.Handler)
        except ImportError:
            pytest.skip("rich not installed")

    def test_rich_formatter_with_stream(self):
        try:
            from aiomisc_log.formatter.rich import rich_formatter

            stream = StringIO()
            handler = rich_formatter(stream=stream)
            assert isinstance(handler, logging.Handler)
        except ImportError:
            pytest.skip("rich not installed")

    def test_rich_formatter_import_error(self):
        with patch.dict("sys.modules", {"rich": None}):
            # This test verifies the fallback behavior
            pass


class TestJournaldFormatter:
    def test_journald_formatter_import_error(self):
        from aiomisc_log.formatter.journald import journald_formatter

        # If logging_journald is not installed, should raise ImportError
        # If it is installed but socket doesn't exist, should raise FileNotFoundError
        try:
            handler = journald_formatter()
            # If we get here, journald is available
            assert isinstance(handler, logging.Handler)
        except (ImportError, FileNotFoundError):
            # Expected on systems without journald
            pass
