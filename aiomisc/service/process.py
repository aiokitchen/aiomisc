import asyncio
import logging
import os
import signal
from abc import ABC, abstractclassmethod
from multiprocessing import Event, Process, synchronize
from typing import Any, Callable, Dict, Optional

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

    _is_running: bool

    async def __is_alive(self) -> Optional[bool]:
        if not hasattr(self, "process"):
            return None

        return await self.loop.run_in_executor(None, self.process.is_alive)

    async def start(self) -> None:
        self._is_running = True

        while self._is_running:
            await super().start()

            if not self.start_event.is_set():
                self.start_event.set()

            while await self.__is_alive():
                await asyncio.sleep(self.process_poll_timeout)

            log.info(
                "Process in service %r exited with code %r, respawning.",
                self, self.process.exitcode,
            )

    async def stop(self, exception: Exception = None) -> Any:
        self._is_running = False
        await super().stop(exception)


__all__ = ("ProcessService", "RespawningProcessService")
