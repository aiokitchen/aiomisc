import logging
import os
import signal
from abc import ABC, abstractclassmethod
from multiprocessing import Event, Process, synchronize
from typing import Any, Callable, Dict, Optional

from aiomisc_log import LOG_FORMAT, LOG_LEVEL, LogFormat, basic_config

from aiomisc.service.base import Service
from aiomisc.periodic import PeriodicCallback

log = logging.getLogger(__name__)


def _process_inner(
    function: Callable[..., Any],
    log_level: str,
    log_format: str,
    start_event: synchronize.Event,
    stop_event: synchronize.Event,
    **kwargs: Any
) -> None:
    basic_config(level=log_level, log_format=log_format)
    start_event.set()
    try:
        function(**kwargs)
    finally:
        stop_event.set()


class ProcessService(Service):
    name: Optional[str] = None
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
            name=self.name,
        )

        process.start()

        await self.loop.run_in_executor(None, self.process_start_event.wait)
        self.process = process

    def __repr__(self) -> str:
        pid: Optional[int] = None
        if hasattr(self, "process"):
            pid = self.process.pid

        return "<{} object at {}: name={!r}, pid={}>".format(
            self.__class__.__name__, hex(id(self)), self.name, pid,
        )

    async def stop(self, exception: Exception = None) -> Any:
        if not self.process.is_alive() or not self.process.pid:
            return

        os.kill(self.process.pid, signal.SIGINT)
        await self.loop.run_in_executor(None, self.process.join)
        await self.loop.run_in_executor(None, self.process_stop_event.wait)


class RespawningProcessService(ProcessService, ABC):
    process_poll_timeout: int = 5

    _supervisor: PeriodicCallback

    async def __supervise(self) -> None:
        if not hasattr(self, "process"):
            return

        if await self.loop.run_in_executor(None, self.process.is_alive):
            return

        log.info(
            "Process in service %r exited with code %r, respawning.",
            self, self.process.exitcode,
        )
        await super().start()

    async def start(self) -> None:
        await super().start()
        self._supervisor = PeriodicCallback(self.__supervise)
        self._supervisor.start(
            self.process_poll_timeout,
        )

    async def stop(self, exception: Exception = None) -> Any:
        await self._supervisor.stop()
        await super().stop(exception)


__all__ = ("ProcessService", "RespawningProcessService")
