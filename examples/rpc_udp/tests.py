import asyncio
import operator
import socket
from functools import reduce
from typing import Any
from collections.abc import Awaitable, Callable

import pytest
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
    return aiomisc_socket_factory(socket.AF_INET, socket.SOCK_DGRAM)


@pytest.fixture
async def rpc_client(localhost, loop) -> RPCServer:
    return RPCServer(handlers=None, address=localhost, port=0)


@pytest.fixture
async def rpc_server(server_port_sock, loop, handlers) -> RPCServer:
    _, sock = server_port_sock
    return RPCServer(handlers=handlers, sock=sock)


@pytest.fixture
def services(rpc_server, rpc_client):
    return [rpc_server, rpc_client]


@pytest.fixture
async def rpc_call(
    server_port_sock, localhost, rpc_client: RPCServer
) -> Callable[..., Awaitable[Any]]:
    port, _ = server_port_sock

    async def call(method, **params) -> Any:
        return await rpc_client(localhost, port, method, **params)

    return call


async def test_foo(rpc_call: Callable[..., Awaitable[Any]]):
    assert await rpc_call("foo") == "bar"


async def test_multiply(rpc_call: Callable[..., Awaitable[Any]]):
    assert await rpc_call("mul", a=1, b=3) == 3


async def test_division(rpc_call: Callable[..., Awaitable[Any]]):
    with pytest.raises(Exception):
        assert await rpc_call("div", a=1, b=0)

    assert await rpc_call("div", a=10, b=5) == 2.0


async def test_many(rpc_call: Callable[..., Awaitable[Any]]):
    calls = []
    expected = []

    for i in range(100):
        calls.append(rpc_call("div", a=i, b=5))
        calls.append(rpc_call("mul", a=i, b=5))

        expected.append(i / 5)
        expected.append(i * 5)

    results = await asyncio.gather(*calls)

    assert results == expected
