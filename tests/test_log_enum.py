import logging
import os
import sys
from io import StringIO
from unittest.mock import patch

import pytest

from aiomisc_log.enum import DateFormat, LogFormat, LogLevel


class TestLogFormat:
    def test_all_values(self):
        assert LogFormat.disabled == -1
        assert LogFormat.stream == 0
        assert LogFormat.color == 1
        assert LogFormat.json == 2
        assert LogFormat.syslog == 3
        assert LogFormat.plain == 4
        assert LogFormat.journald == 5
        assert LogFormat.rich == 6
        assert LogFormat.rich_tb == 7

    def test_choices(self):
        choices = LogFormat.choices()
        assert isinstance(choices, tuple)
        assert "disabled" in choices
        assert "stream" in choices
        assert "color" in choices
        assert "json" in choices
        assert "syslog" in choices
        assert "plain" in choices
        assert "journald" in choices
        assert "rich" in choices
        assert "rich_tb" in choices
        assert len(choices) == 9

    def test_default_non_tty(self):
        # Mock non-tty stderr and no journal stream
        mock_stderr = StringIO()
        mock_stderr.fileno = lambda: 999

        with (
            patch("aiomisc_log.enum.check_journal_stream", return_value=False),
            patch("os.isatty", return_value=False),
            patch.object(sys, "stderr", mock_stderr),
        ):
            result = LogFormat.default()
            assert result == "plain"

    def test_default_tty_with_rich(self):
        mock_stderr = StringIO()
        mock_stderr.fileno = lambda: 999

        with (
            patch("aiomisc_log.enum.check_journal_stream", return_value=False),
            patch("os.isatty", return_value=True),
            patch.object(sys, "stderr", mock_stderr),
            patch("aiomisc_log.enum.RICH_INSTALLED", True),
        ):
            result = LogFormat.default()
            assert result == "rich"

    def test_default_tty_without_rich(self):
        mock_stderr = StringIO()
        mock_stderr.fileno = lambda: 999

        with (
            patch("aiomisc_log.enum.check_journal_stream", return_value=False),
            patch("os.isatty", return_value=True),
            patch.object(sys, "stderr", mock_stderr),
            patch("aiomisc_log.enum.RICH_INSTALLED", False),
        ):
            result = LogFormat.default()
            assert result == "color"

    def test_default_journald(self):
        with patch("aiomisc_log.enum.check_journal_stream", return_value=True):
            result = LogFormat.default()
            assert result == "journald"


class TestLogLevel:
    def test_all_values(self):
        assert LogLevel.critical == logging.CRITICAL
        assert LogLevel.error == logging.ERROR
        assert LogLevel.warning == logging.WARNING
        assert LogLevel.info == logging.INFO
        assert LogLevel.debug == logging.DEBUG
        assert LogLevel.notset == logging.NOTSET

    def test_choices(self):
        choices = LogLevel.choices()
        assert isinstance(choices, tuple)
        assert "critical" in choices
        assert "error" in choices
        assert "warning" in choices
        assert "info" in choices
        assert "debug" in choices
        assert "notset" in choices
        assert len(choices) == 6

    def test_default(self):
        assert LogLevel.default() == "info"


class TestDateFormat:
    def test_all_values(self):
        assert DateFormat.color.value == "%Y-%m-%d %H:%M:%S"
        assert DateFormat.stream.value == "[%Y-%m-%d %H:%M:%S]"
        assert DateFormat.json.value == "%s"
        assert DateFormat.syslog.value is None
        assert DateFormat.rich.value == "[%X]"
