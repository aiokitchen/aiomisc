import logging
import os
import signal
from abc import abstractclassmethod
from multiprocessing import Event, Process, synchronize
from typing import Any, Callable, Dict

from aiomisc_log import LOG_FORMAT, LOG_LEVEL, LogFormat, basic_config

from .base import Service


log = logging.getLogger(__name__)


def _process_inner(
    function: Callable[..., Any],
    log_level: str,
    log_format: str,
    start_event: synchronize.Event,
    stop_event: synchronize.Event,
    **kwargs: Any
) -> None:
    basic_config(level=log_level, format=log_format)
    start_event.set()
    try:
        function(**kwargs)
    finally:
        stop_event.set()


class ProcessService(Service):
    process: Process
    process_start_event: synchronize.Event
    process_stop_event: synchronize.Event

    def get_process_kwargs(self) -> Dict[str, Any]:
        return {}

    @abstractclassmethod
    def in_process(cls, **kwargs: Any) -> Any:
        pass

    async def start(self) -> Any:
        self.process_start_event = Event()
        self.process_stop_event = Event()
        log_level = (
            log.getEffectiveLevel()
            if LOG_LEVEL is None
            else LOG_LEVEL.get()
        )
        log_format = (
            LogFormat.default()
            if LOG_FORMAT is None
            else LOG_FORMAT.get().value
        )

        process = Process(
            target=_process_inner,
            args=(
                self.in_process,
                log_level,
                log_format,
                self.process_start_event,
                self.process_stop_event,
            ),
            kwargs=self.get_process_kwargs(),
        )

        process.start()

        await self.loop.run_in_executor(None, self.process_start_event.wait)

    async def stop(self, exception: Exception = None) -> Any:
        if not self.process.is_alive() or not self.process.pid:
            return

        os.kill(self.process.pid, signal.SIGINT)
        await self.loop.run_in_executor(None, self.process.join)
        await self.loop.run_in_executor(None, self.process_stop_event.wait)


__all__ = ("ProcessService",)
