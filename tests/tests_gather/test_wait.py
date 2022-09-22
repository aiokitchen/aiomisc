from asyncio import create_task

from aiomisc import wait_first_cancelled_or_exception
from tests.tests_gather.conftest import ok, fail, cancel


async def test_wait_ok():
    tasks = [
        create_task(ok(0.01)),
        create_task(ok(0.02)),
        create_task(ok(0.03)),
    ]
    done, pending = await wait_first_cancelled_or_exception(tasks)
    assert done == set(tasks)
    assert not pending
    for task in done:
        assert task.done()
        assert await task


async def test_wait_timeout():
    tasks = [
        create_task(ok(0.01)),
        create_task(ok(0.02)),
        create_task(ok(0.03)),
    ]
    done, pending = await wait_first_cancelled_or_exception(
        tasks, timeout=0.015,
    )
    assert done == set(tasks[:1])
    assert pending == set(tasks[1:])
    for task in done:
        assert task.done()
        assert await task
    for task in pending:
        assert not task.done()


async def test_wait_fail():
    tasks = [
        create_task(ok(0.01)),
        create_task(fail(0.02)),
        create_task(cancel(0.03)),
    ]

    done, pending = await wait_first_cancelled_or_exception(tasks)
    assert done == {tasks[0], tasks[1]}
    assert pending == {tasks[2]}

    assert tasks[0].done() and await tasks[0]
    assert tasks[1].done() and tasks[1].exception()
    assert not tasks[2].done()


async def test_wait_cancel():
    tasks = [
        create_task(ok(0.01)),
        create_task(cancel(0.02)),
        create_task(fail(0.03)),
    ]

    done, pending = await wait_first_cancelled_or_exception(tasks)
    assert done == {tasks[0], tasks[1]}
    assert pending == {tasks[2]}

    assert tasks[0].done() and await tasks[0]
    assert tasks[1].done() and tasks[1].cancelled()
    assert not tasks[2].done()
