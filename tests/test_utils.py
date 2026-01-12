import asyncio
import json
import logging
import socket
import time
import uuid
from random import shuffle
from typing import List, Optional
from collections.abc import Sequence

import pytest

import aiomisc

pytestmark = pytest.mark.catch_loop_exceptions


async def test_select(event_loop: asyncio.AbstractEventLoop):
    f_one = asyncio.Event()
    f_two = asyncio.Event()

    event_loop.call_soon(f_one.set)
    event_loop.call_later(1, f_two.set)

    two, one = await aiomisc.select(f_two.wait(), f_one.wait())

    assert one
    assert two is None

    one, two = await aiomisc.select(f_one.wait(), f_two.wait())
    assert one


async def test_select_cancelling(event_loop: asyncio.AbstractEventLoop):
    results: list[bool | None] = []

    async def good_coro(wait):
        try:
            if wait:
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(0)
                results.append(True)
                return True
        finally:
            results.append(None)

    one, two = await aiomisc.select(good_coro(False), good_coro(True))
    assert one
    assert results[0]
    assert results[1] is None


async def test_select_exception(event_loop: asyncio.AbstractEventLoop):
    event = asyncio.Event()

    async def bad_coro():
        if event.is_set():
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(0)
            raise ZeroDivisionError

    with pytest.raises(ZeroDivisionError):
        await aiomisc.select(bad_coro(), bad_coro())


@aiomisc.timeout(1)
async def test_select_cancel_false(event_loop: asyncio.AbstractEventLoop):
    event1 = asyncio.Event()
    event2 = asyncio.Event()
    event3 = asyncio.Event()

    async def coro1():
        await event1.wait()
        event2.set()

    async def coro2():
        event1.set()
        await event2.wait()
        event3.set()

    await aiomisc.select(coro2(), coro1(), cancel=False)
    await event3.wait()


@aiomisc.timeout(1)
async def test_select_cancel_true(event_loop: asyncio.AbstractEventLoop):
    event1 = asyncio.Event()
    event2 = asyncio.Event()
    event3 = asyncio.Event()

    async def coro1():
        await event1.wait()
        event2.set()

    async def coro2():
        await asyncio.sleep(0)
        event3.set()

    await aiomisc.select(coro2(), coro1(), cancel=True)
    assert not event1.is_set()
    assert not event2.is_set()


def test_shield():
    results = []

    @aiomisc.shield
    async def coro():
        await asyncio.sleep(0.5)
        results.append(True)

    async def main(event_loop):
        task = event_loop.create_task(coro())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            await asyncio.sleep(1)

    with aiomisc.entrypoint() as event_loop:
        event_loop.run_until_complete(
            asyncio.wait_for(main(event_loop), timeout=10)
        )

    assert results == [True]


def test_chunk_list():
    data: Sequence[Sequence[int]] = tuple(
        map(tuple, aiomisc.chunk_list(range(10), 3))
    )

    assert data == ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9,))


def test_configure_logging_json(capsys):
    data = str(uuid.uuid4())

    aiomisc.log.basic_config(
        level=logging.DEBUG, log_format="json", buffered=False
    )
    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    json_result = json.loads(stdout.strip())
    assert json_result["msg"] == data

    logging.basicConfig(handlers=[], level=logging.INFO)


def test_configure_logging_stderr(capsys):
    data = str(uuid.uuid4())

    out, err = capsys.readouterr()

    # logging.basicConfig(level=logging.INFO)
    aiomisc.log.basic_config(
        level=logging.DEBUG, log_format="stream", buffered=False
    )

    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    assert data in stderr

    logging.basicConfig(handlers=[])


BIND_CASES = [
    ("127.0.0.1", socket.AF_INET),
    ("0.0.0.0", socket.AF_INET),
    ("::", socket.AF_INET6),
]


@pytest.mark.parametrize("address,family", BIND_CASES)
def test_bind_address(address, family, aiomisc_unused_port):
    sock = aiomisc.bind_socket(address=address, port=aiomisc_unused_port)

    assert isinstance(sock, socket.socket)
    assert sock.family == family


async def test_cancel_tasks(event_loop):
    semaphore = asyncio.Semaphore(10)

    tasks = [event_loop.create_task(semaphore.acquire()) for _ in range(20)]

    done, pending = await asyncio.wait(tasks, timeout=0.5)

    for task in pending:
        assert not task.done()

    for task in done:
        assert task.done()

    await aiomisc.cancel_tasks(pending)

    assert len(done) == 10
    assert len(pending) == 10

    for task in pending:
        assert task.done()

        with pytest.raises(asyncio.CancelledError):
            await task


async def test_cancel_tasks_futures(event_loop):
    counter = 0

    def create_future():
        nonlocal counter

        future = event_loop.create_future()
        counter += 1

        if counter <= 10:
            event_loop.call_soon(future.set_result, True)

        return future

    tasks = [create_future() for _ in range(20)]

    await asyncio.sleep(0.5)

    done = tasks[:10]
    pending = tasks[10:]

    for task in pending:
        assert not task.done()

    for task in done:
        assert task.done()

    await aiomisc.cancel_tasks(pending)

    assert len(done) == 10
    assert len(pending) == 10

    for task in pending:
        assert type(task) is asyncio.Future
        assert task.done()

        with pytest.raises(asyncio.CancelledError):
            await task


async def test_cancel_tasks_futures_and_tasks(event_loop):
    tasks = []

    counter = 0

    def create_future():
        nonlocal counter

        future = event_loop.create_future()
        counter += 1

        if counter <= 10:
            event_loop.call_soon(future.set_result, True)

        return future

    for _ in range(20):
        tasks.append(create_future())

    semaphore = asyncio.Semaphore(10)

    for _ in range(20):
        tasks.append(event_loop.create_task(semaphore.acquire()))

    shuffle(tasks)

    done, pending = await asyncio.wait(tasks, timeout=0.5)

    for task in pending:
        assert not task.done()

    for task in done:
        assert task.done()

    await aiomisc.cancel_tasks(pending)

    assert len(done) == 20
    assert len(pending) == 20

    for task in pending:
        assert task.done()

        with pytest.raises(asyncio.CancelledError):
            await task


async def test_awaitable_decorator(event_loop):
    future = event_loop.create_future()
    event_loop.call_soon(future.set_result, 654321)

    @aiomisc.awaitable
    def no_awaitable():
        return 654321

    @aiomisc.awaitable
    def pass_future():
        return future

    @aiomisc.awaitable
    async def coro():
        return await future

    assert pass_future() is future

    assert (await coro()) == 654321
    assert (await pass_future()) == 654321
    assert (await no_awaitable()) == 654321


def test_create_default_event_loop():
    loop, _ = aiomisc.utils.create_default_event_loop()

    async def run():
        with pytest.raises(RuntimeError):
            aiomisc.utils.create_default_event_loop()

    loop.run_until_complete(run())
