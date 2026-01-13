import asyncio
import operator
from functools import reduce

import pytest
from rpc.client import RPCClient
from rpc.server import RPCServer


@pytest.fixture
def handlers():
    return {
        "foo": lambda: "bar",
        "mul": lambda **a: reduce(operator.mul, a.values()),
        "div": lambda **a: reduce(operator.truediv, a.values()),
    }


@pytest.fixture
def server_port_sock(aiomisc_socket_factory):
    return aiomisc_socket_factory()


@pytest.fixture
def rpc_server(server_port_sock, handlers):
    _, sock = server_port_sock
    return RPCServer(handlers=handlers, sock=sock)


@pytest.fixture
async def rpc_client(server_port_sock, localhost, handlers) -> RPCClient:
    port, _ = server_port_sock
    return RPCClient(address=localhost, port=port, handlers=handlers)


@pytest.fixture
def services(rpc_server, rpc_client):
    return [rpc_server, rpc_client]


async def test_foo(rpc_client: RPCClient):
    assert await rpc_client("foo") == "bar"


async def test_multiply(rpc_client: RPCClient):
    assert await rpc_client("mul", a=1, b=3) == 3


async def test_division(rpc_client: RPCClient):
    with pytest.raises(Exception):
        assert await rpc_client("div", a=1, b=0)

    assert await rpc_client("div", a=10, b=5) == 2.0


async def test_many(rpc_client: RPCClient):
    calls = []
    expected = []

    for i in range(100):
        calls.append(rpc_client("div", a=i, b=5))
        calls.append(rpc_client("mul", a=i, b=5))

        expected.append(i / 5)
        expected.append(i * 5)

    results = await asyncio.gather(*calls)

    assert results == expected


async def test_two_way(rpc_client: RPCClient, rpc_server: RPCServer):
    assert await rpc_server("div", a=100, b=10) == await rpc_client(
        "div", a=100, b=10
    )
