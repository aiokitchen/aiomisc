import asyncio
import json
import logging
import socket
import time
import uuid
import pytest

import aiomisc


def test_shield():
    results = []

    @aiomisc.shield
    async def coro():
        nonlocal results
        await asyncio.sleep(0.5)
        results.append(True)

    async def main(loop):
        task = loop.create_task(coro())
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            await asyncio.sleep(1)

    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main(loop))

    assert results == [True]


def test_chunk_list():
    data = tuple(map(tuple, aiomisc.chunk_list(range(10), 3)))

    assert data == ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9,))


def test_configure_logging_json(capsys):
    data = str(uuid.uuid4())

    aiomisc.log.basic_config(
        level=logging.DEBUG, log_format='json', buffered=False
    )
    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    json_result = json.loads(stdout.strip())
    assert json_result['msg'] == data

    logging.basicConfig(handlers=[], level=logging.INFO)


def test_configure_logging_stderr(capsys):
    data = str(uuid.uuid4())

    out, err = capsys.readouterr()

    # logging.basicConfig(level=logging.INFO)
    aiomisc.log.basic_config(level=logging.DEBUG,
                             log_format='stream', buffered=False)

    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    assert data in stderr

    logging.basicConfig(handlers=[])


@pytest.mark.parametrize("address,family", [
    ("127.0.0.1", socket.AF_INET),
    ("0.0.0.0", socket.AF_INET),
    ("::", socket.AF_INET6),
])
def test_bind_address(address, family, aiomisc_unused_port):
    sock = aiomisc.bind_socket(address=address, port=aiomisc_unused_port)

    assert isinstance(sock, socket.socket)
    assert sock.family == family


async def test_select(loop: asyncio.AbstractEventLoop):
    f_one = loop.create_future()
    f_two = loop.create_future()

    loop.call_soon(f_one.set_result, True)
    loop.call_later(1, f_two.set_result, True)

    one, two = await aiomisc.select(f_one, f_two)

    assert one
    assert two is None

    one, two = await aiomisc.select(f_one, f_two)
    assert one


async def test_select_cancelling(loop: asyncio.AbstractEventLoop):
    results = []

    async def good_coro():
        nonlocal results

        try:
            if results:
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(0)
                results.append(True)
                return True
        finally:
            results.append(None)

    one, two = await aiomisc.select(good_coro(), good_coro())
    assert one
    assert results[0]
    assert results[1] is None


async def test_select_exception(loop: asyncio.AbstractEventLoop):
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
async def test_select_cancel_false(loop: asyncio.AbstractEventLoop):
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
async def test_select_cancel_true(loop: asyncio.AbstractEventLoop):
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
