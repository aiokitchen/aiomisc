import asyncio
import hashlib
import time

import pytest

import aiomisc


class HashServer(aiomisc.service.TCPServer):
    async def handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        hasher = hashlib.md5()

        while not reader.at_eof():
            chunk = await reader.read(65534)
            if not chunk:
                writer.close()
                await writer.wait_closed()
                return

            hasher.update(chunk)
            writer.write(hasher.digest())


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
async def proxy(tcp_proxy, localhost, server_port):
    proxy = tcp_proxy(localhost, server_port)

    try:
        yield proxy
    finally:
        await asyncio.wait_for(proxy.close(), timeout=1)


@pytest.fixture()
async def proxy_client(proxy):
    await proxy.start(timeout=1)

    return await asyncio.wait_for(
        asyncio.open_connection(proxy.proxy_host, proxy.proxy_port), timeout=1,
    )


async def test_proxy_client(proxy_client, proxy):
    reader, writer = proxy_client
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=1)

    assert hash == hashlib.md5(payload).digest()


async def test_proxy_client_close(proxy_client, proxy):
    reader, writer = proxy_client
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=1)

    assert hash == hashlib.md5(payload).digest()

    assert not reader.at_eof()
    await proxy.disconnect_all()

    assert await asyncio.wait_for(reader.read(), timeout=1) == b""
    assert reader.at_eof()


async def test_proxy_client_slow(proxy_client, proxy):
    delay = 0.1
    proxy.set_delay(delay)

    reader, writer = proxy_client
    payload = b"Hello world"

    delta = -time.monotonic()
    writer.write(payload)
    hash = await asyncio.wait_for(reader.readexactly(16), timeout=2)
    delta += time.monotonic()

    assert delta >= delay, [c.delay for c in proxy.clients]

    assert hash == hashlib.md5(payload).digest()


async def test_proxy_client_with_processor(proxy_client, proxy):
    processed_request = b"Never say hello"
    processed_response = b"Yeah"

    proxy.set_content_processors(
        lambda _: processed_request,
        lambda _: processed_response,
    )

    reader, writer = proxy_client
    payload = b"Hello world"

    writer.write(payload)
    hash = await asyncio.wait_for(reader.read(16), timeout=2)

    assert hash == processed_response
