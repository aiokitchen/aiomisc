import asyncio
import json
import logging
import socket
import time
import uuid

import pytest

from aiomisc.entrypoint import entrypoint
from aiomisc.utils import chunk_list, bind_socket, wait_for
from aiomisc.log import basic_config


def test_chunk_list(event_loop):
    data = tuple(map(tuple, chunk_list(range(10), 3)))

    assert data == ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9,))


def test_configure_logging_json(capsys):
    data = str(uuid.uuid4())

    basic_config(level=logging.DEBUG, log_format='json', buffered=False)
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
    basic_config(level=logging.DEBUG, log_format='stream', buffered=False)

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
def test_bind_address(address, family, unused_tcp_port):
    sock = bind_socket(address=address, port=unused_tcp_port)

    assert isinstance(sock, socket.socket)
    assert sock.family == family


def test_wait_for_dummy():
    with entrypoint() as loop:
        results = loop.run_until_complete(
            wait_for(*[asyncio.sleep(0.1) for _ in range(100)])
        )

    assert len(results) == 100
    assert results == [None] * 100


def test_wait_for_exception():
    async def coro(arg):
        await asyncio.sleep(0.1)
        assert arg != 15
        return arg

    with entrypoint() as loop:
        with pytest.raises(AssertionError):
            loop.run_until_complete(
                wait_for(*[coro(i) for i in range(100)])
            )

        results = loop.run_until_complete(
            wait_for(
                *[coro(i) for i in range(17)],
                raise_first=False
            ),
        )

    assert results
    assert len(results) == 17
    assert isinstance(results[15], AssertionError)
    assert results[:15] == [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]
    assert results[16:] == [16]


def test_wait_for_cancelling():
    results = []

    async def coro(arg):
        nonlocal results
        await asyncio.sleep(0.1)
        assert arg != 15

        if arg > 15:
            await asyncio.sleep(1)

        results.append(arg)

    with entrypoint() as loop:
        with pytest.raises(AssertionError):
            loop.run_until_complete(
                wait_for(*[coro(i) for i in range(100)])
            )

        loop.run_until_complete(asyncio.sleep(2))

    assert results
    assert len(results) == 15
    assert len(set(results)) == 15
    assert frozenset(results) == frozenset(range(15))
