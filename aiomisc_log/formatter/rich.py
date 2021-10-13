import logging
import sys
from typing import IO, Any

from aiomisc_log.enum import DateFormat


try:
    from rich.console import Console
    from rich.logging import RichHandler

    def rich_formatter(
        date_format: str = None, stream: IO[str] = None,
        rich_tracebacks: bool = False, **_: Any
    ) -> logging.Handler:
        handler = RichHandler(
            console=Console(file=stream or sys.stderr),
            log_time_format=date_format or DateFormat.rich.value,
            rich_tracebacks=rich_tracebacks,
        )
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        return handler
except ImportError:
    def rich_formatter(
        date_format: str = None, stream: IO[str] = None,
        rich_tracebacks: bool = False, **_: Any
    ) -> logging.Handler:
        raise ImportError("You must install \"rich\" library for use it")
