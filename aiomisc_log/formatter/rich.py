import logging
from typing import IO, Any, Optional

from aiomisc_log.enum import DateFormat


try:
    from rich import reconfigure
    from rich.logging import RichHandler

    def rich_formatter(
        date_format: Optional[str] = None, stream: Optional[IO[str]] = None,
        **kwargs: Any,
    ) -> logging.Handler:
        kwargs.setdefault("rich_tracebacks", False)
        kwargs.setdefault(
            "log_time_format", date_format or DateFormat.rich.value,
        )

        if "console" not in kwargs:
            if stream is None:
                reconfigure(stderr=True)
            else:
                reconfigure(file=stream)

        handler = RichHandler(**kwargs)
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        return handler
except ImportError:
    def rich_formatter(
        date_format: Optional[str] = None, stream: Optional[IO[str]] = None,
        **kwargs: Any,
    ) -> logging.Handler:
        raise ImportError("You must install \"rich\" library for use it")
