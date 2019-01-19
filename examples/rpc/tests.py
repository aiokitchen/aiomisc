import asyncio
import operator
from functools import reduce

import pytest

from .server import RPCServer
from .client import RPCClient


@pytest.fixture
def server_port(aiomisc_unused_port):
    return aiomisc_unused_port


@pytest.fixture
def handlers():
    return {
        'foo': lambda: 'bar',
        'mul': lambda **a: reduce(operator.mul, a.values()),
        'div': lambda **a: reduce(operator.truediv, a.values()),
    }


@pytest.fixture
def services(server_port, handlers):
    return [
        RPCServer(
            handlers=handlers,
            address='localhost',
            port=server_port
        )
    ]


@pytest.fixture
async def rpc_client(request, server_port) -> RPCClient:
    reader, writer = await asyncio.open_connection(
        'localhost', server_port
    )

    try:
        client = RPCClient(reader, writer)
        yield client
    finally:
        await client.close()


async def test_foo(rpc_client):
    assert await rpc_client('foo') == 'bar'


async def test_multiply(rpc_client):
    assert await rpc_client('mul', a=1, b=3) == 3


async def test_division(rpc_client):
    with pytest.raises(Exception):
        assert await rpc_client('div', a=1, b=0)

    assert await rpc_client('div', a=10, b=5) == 2.


async def test_many(rpc_client):
    calls = []
    expected = []

    for i in range(100):
        calls.append(rpc_client('div', a=i, b=5))
        calls.append(rpc_client('mul', a=i, b=5))

        expected.append(i / 5)
        expected.append(i * 5)

    results = await asyncio.gather(*calls)

    assert results == expected
