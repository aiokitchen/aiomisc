import logging
from typing import Any


try:
    from logging_journald import JournaldLogHandler  # type: ignore

    def journald_formatter(**_: Any) -> logging.Handler:
        if not JournaldLogHandler.SOCKET_PATH.exists():
            raise FileNotFoundError("JournalD socket doesn't exists")

        handler = JournaldLogHandler()
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        return handler

except ImportError:
    def journald_formatter(**_: Any) -> logging.Handler:
        raise ImportError(
            "You must install \"logging-journald\" library for use it",
        )
