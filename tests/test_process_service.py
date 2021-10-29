from pathlib import Path
from typing import Any, Dict

import pytest

import aiomisc
from aiomisc.service.process import ProcessService


pytestmark = pytest.mark.catch_loop_exceptions


class TestProcessService(ProcessService):
    __required__ = ("path",)

    path: Path

    def get_process_kwargs(self) -> Dict[str, Any]:
        return dict(path=str(self.path))

    @classmethod
    def in_process(cls, *, path: str) -> Any:
        with open(path, "w") as fp:
            fp.write("Hello world\n")


def test_service(tmpdir):
    tmp_path = Path(tmpdir)
    test_file = tmp_path / "test.txt"
    svc = TestProcessService(path=test_file)

    async def wait(loop):
        loop.run_in_executor(None, svc.process_stop_event.wait)

    with aiomisc.entrypoint(svc) as loop:
        loop.run_until_complete(wait(loop))

    with open(test_file) as fp:
        assert fp.readline() == "Hello world\n"
