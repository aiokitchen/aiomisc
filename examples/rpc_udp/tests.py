import asyncio
import operator
from functools import partial, reduce

import pytest

from .client import RPCClientUDPProtocol
from .server import RPCServer


@pytest.fixture
def server_port(aiomisc_unused_port):
    return aiomisc_unused_port


@pytest.fixture
def handlers():
    return {
        "foo": lambda: "bar",
        "mul": lambda **a: reduce(operator.mul, a.values()),
        "div": lambda **a: reduce(operator.truediv, a.values()),
    }


@pytest.fixture
def services(server_port, handlers):
    return [
        RPCServer(
            handlers=handlers,
            address="localhost",
            port=server_port,
        ),
    ]


@pytest.fixture
async def rpc_client(
        server_port, aiomisc_unused_port_factory, localhost, loop
) -> RPCClientUDPProtocol:
    transport, protocol = await loop.create_datagram_endpoint(
        RPCClientUDPProtocol,
        local_addr=(localhost, aiomisc_unused_port_factory()),
    )

    try:
        yield partial(protocol.rpc, (localhost, server_port))
    finally:
        transport.close()


async def test_foo(rpc_client):
    assert await rpc_client("foo") == "bar"


async def test_multiply(rpc_client):
    assert await rpc_client("mul", a=1, b=3) == 3


async def test_division(rpc_client):
    with pytest.raises(Exception):
        assert await rpc_client("div", a=1, b=0)

    assert await rpc_client("div", a=10, b=5) == 2.


async def test_many(rpc_client):
    calls = []
    expected = []

    for i in range(100):
        calls.append(rpc_client("div", a=i, b=5))
        calls.append(rpc_client("mul", a=i, b=5))

        expected.append(i / 5)
        expected.append(i * 5)

    results = await asyncio.gather(*calls)

    assert results == expected
