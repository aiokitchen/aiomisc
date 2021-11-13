import os
from multiprocessing import Queue
from pathlib import Path
from typing import Any, Dict

import pytest

import aiomisc
from aiomisc import threaded, timeout
from aiomisc.service import ProcessService, RespawningProcessService


pytestmark = pytest.mark.catch_loop_exceptions


def test_abstractmethod_exception():
    with pytest.raises(TypeError):
        ProcessService()


class SampleProcessService(ProcessService):
    __required__ = ("path",)

    path: Path

    def get_process_kwargs(self) -> Dict[str, Any]:
        return dict(path=str(self.path))

    @classmethod
    def in_process(cls, *, path: str) -> Any:
        with open(path, "w") as fp:
            fp.write("Hello world\n")


def test_process_service(tmpdir):
    tmp_path = Path(tmpdir)
    test_file = tmp_path / "test.txt"
    svc = SampleProcessService(path=test_file)

    async def wait(loop):
        loop.run_in_executor(None, svc._process_stop_event.wait)

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(wait(loop))

    with open(test_file) as fp:
        assert fp.readline() == "Hello world\n"


class SimpleRespawningProcessService(RespawningProcessService):
    __required__ = ("queue",)

    queue: Queue

    def get_process_kwargs(self) -> Dict[str, Any]:
        return dict(queue=self.queue)

    @classmethod
    def in_process(cls, *, queue: Queue) -> Any:
        queue.put(os.getpid())


@pytest.mark.skip("temporary skip")
def test_respawning_process_service(tmpdir):
    queue = Queue()
    svc = SimpleRespawningProcessService(
        queue=queue,
        process_poll_timeout=0.5,
    )

    @timeout(5)
    async def go():
        pids = []

        @threaded
        def getter():
            return queue.get()

        for _ in range(2):
            pids.append(await getter())

        assert len(pids) == 2
        assert pids[0] != pids[1]

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(go())
