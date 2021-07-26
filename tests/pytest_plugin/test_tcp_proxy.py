import asyncio
import hashlib
import time

import pytest
from async_generator import async_generator, yield_

import aiomisc


class HashServer(aiomisc.service.TCPServer):
    async def handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ):
        hasher = hashlib.md5()

        chunk = await reader.read(65534)
        while chunk:
            hasher.update(chunk)
            writer.write(hasher.digest())
            chunk = await reader.read(65534)

        writer.close()
        await writer.wait_closed()


@pytest.fixture()
def server_port(aiomisc_unused_port_factory) -> int:
    return aiomisc_unused_port_factory()


@pytest.fixture()
def service(
    loop: asyncio.AbstractEventLoop,
    server_port, localhost,
) -> HashServer:
    return HashServer(port=server_port, address=localhost)


@pytest.fixture()
def services(service: HashServer):
    return [service]


@pytest.fixture()
@async_generator
async def proxy(tcp_proxy, localhost, server_port):
    async with tcp_proxy(localhost, server_port, buffered=True) as proxy:
        await yield_(proxy)


async def test_proxy_client(proxy):
    reader, writer = await proxy.create_client()
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=1)

    assert hash == hashlib.md5(payload).digest()


async def test_proxy_client_close(proxy):
    reader, writer = await proxy.create_client()
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=1)

    assert hash == hashlib.md5(payload).digest()

    assert not reader.at_eof()
    await proxy.disconnect_all()

    assert await asyncio.wait_for(reader.read(), timeout=1) == b""
    assert reader.at_eof()


async def test_proxy_client_slow(proxy):
    delay = 0.1
    proxy.set_delay(delay, delay)

    reader, writer = await proxy.create_client()
    payload = b"Hello world"

    delta = -time.monotonic()
    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=2)
    delta += time.monotonic()

    assert delta >= delay, [c.delay for c in proxy.clients]

    assert hash == hashlib.md5(payload).digest()


async def test_proxy_client_with_processor(proxy):
    processed_request = b"Never say hello"

    proxy.set_content_processors(
        lambda _: processed_request,
        lambda chunk: chunk[::-1],
    )

    reader, writer = await proxy.create_client()
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.read(16), timeout=2)

    assert hash == hashlib.md5(processed_request).digest()[::-1]
