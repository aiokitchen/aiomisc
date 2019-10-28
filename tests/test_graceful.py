import asyncio
from asyncio import CancelledError, Task

import pytest

from aiomisc.service.graceful import GracefulMixin, GracefulService


async def test_graceful():
    class Graceful(GracefulMixin):
        pass

    async def pho():
        pass

    graceful = Graceful()

    task = graceful.create_graceful_task(pho(), cancel=False)
    assert isinstance(task, Task)

    await asyncio.sleep(0.1)

    # Check that done and popped itself from the task store
    assert task.done()
    assert not graceful._GracefulMixin__tasks


@pytest.mark.parametrize(
    'cancel,expected', [
        (False, None),
        (True, CancelledError),
    ]
)
async def test_graceful_shutdown(cancel, expected):
    class Graceful(GracefulMixin):
        pass

    async def pho():
        await asyncio.sleep(0.1)

    graceful = Graceful()

    task = graceful.create_graceful_task(pho(), cancel=cancel)
    assert isinstance(task, Task)

    await graceful.graceful_shutdown()
    assert task.done()

    if expected is None:
        assert not task.exception()
    else:
        with pytest.raises(CancelledError):
            task.exception()

    assert not graceful._GracefulMixin__tasks


async def test_graceful_service():
    class TestService(GracefulService):

        task_wait = None
        task_cancel = None

        async def start(self):
            self.task_wait = self.create_graceful_task(
                self.pho(), cancel=False
            )
            self.task_cancel = self.create_graceful_task(
                self.pho(), cancel=True
            )

        async def pho(self):
            await asyncio.sleep(0.1)

    service = TestService()

    await service.start()
    await service.stop()

    assert service.task_wait.done()
    assert service.task_cancel.done()

    assert not service.task_wait.exception()
    with pytest.raises(CancelledError):
        service.task_cancel.exception()

    assert not service._GracefulMixin__tasks
