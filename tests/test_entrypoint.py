import asyncio
import os
import socket
from tempfile import mktemp

import pytest
from aiomisc.entrypoint import entrypoint
from aiomisc.service import Service, TCPServer, UDPServer
from aiomisc.thread_pool import threaded


@pytest.fixture()
def unix_socket_udp():
    socket_path = mktemp(dir='/tmp', suffix='.sock')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.setblocking(False)

    try:
        sock.bind(socket_path)
        yield sock
    except:
        pass
    else:
        sock.close()
    finally:
        if os.path.exists(socket_path):
            os.remove(socket_path)


@pytest.fixture()
def unix_socket_tcp():
    socket_path = mktemp(dir='/tmp', suffix='.sock')
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.setblocking(False)

    try:
        sock.bind(socket_path)
        yield sock
    except:
        pass
    else:
        sock.close()
    finally:
        if os.path.exists(socket_path):
            os.remove(socket_path)


def test_service_class():
    with pytest.raises(NotImplementedError):
        services = (
            Service(running=False, stopped=False),
            Service(running=False, stopped=False),
        )

        with entrypoint(*services):
            pass


def test_simple():
    class StartingService(Service):
        async def start(self):
            self.running = True

    class DummyService(StartingService):
        async def stop(self, err: Exception = None):
            self.stopped = True

    services = (
        DummyService(running=False, stopped=False),
        DummyService(running=False, stopped=False),
    )

    with entrypoint(*services):
        pass

    for svc in services:
        assert svc.running
        assert svc.stopped

    services = (
        DummyService(running=False, stopped=False),
        DummyService(running=False, stopped=False),
    )

    with entrypoint(*services):
        raise RuntimeError

    for svc in services:
        assert svc.running
        assert svc.stopped

    services = (
        StartingService(running=False),
        StartingService(running=False),
    )

    with entrypoint(*services):
        raise RuntimeError

    for svc in services:
        assert svc.running


def test_wrong_sublclass():
    with pytest.raises(TypeError):
        class _(Service):
            def start(self):
                return True

    class MyService(Service):
        async def start(self):
            return

    with pytest.raises(TypeError):
        class _(MyService):
            def stop(self):
                return True

    class _(MyService):
        async def stop(self):
            return True


def test_tcp_server(unused_tcp_port):
    class TestService(TCPServer):
        DATA = []

        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            self.DATA.append(await reader.readline())
            writer.close()

    service = TestService('127.0.0.1', unused_tcp_port)

    @threaded
    def writer():
        with socket.create_connection(('127.0.0.1', unused_tcp_port)) as sock:
            sock.send(b'hello server\n')

    with entrypoint(service) as loop:
        loop.run_until_complete(writer())

    assert TestService.DATA
    assert TestService.DATA == [b'hello server\n']


def test_udp_server(unused_tcp_port):
    class TestService(UDPServer):
        DATA = []

        async def handle_datagram(self, data: bytes, addr: tuple):
            self.DATA.append(data)

    service = TestService('127.0.0.1', unused_tcp_port)

    @threaded
    def writer():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        with sock:
            sock.sendto(b'hello server\n', ('127.0.0.1', unused_tcp_port))

    with entrypoint(service) as loop:
        loop.run_until_complete(writer())

    assert TestService.DATA
    assert TestService.DATA == [b'hello server\n']


def test_udp_socket_server(unix_socket_udp):
    class TestService(UDPServer):
        DATA = []

        async def handle_datagram(self, data: bytes, addr: tuple):
            self.DATA.append(data)

    service = TestService(sock=unix_socket_udp)

    @threaded
    def writer():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        with sock:
            sock.sendto(b'hello server\n', unix_socket_udp.getsockname())

    with entrypoint(service) as loop:
        loop.run_until_complete(writer())

    assert TestService.DATA
    assert TestService.DATA == [b'hello server\n']


def test_tcp_server_unix(unix_socket_tcp):
    class TestService(TCPServer):
        DATA = []

        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            self.DATA.append(await reader.readline())
            writer.close()

    service = TestService(sock=unix_socket_tcp)

    @threaded
    def writer():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(unix_socket_tcp.getsockname())
            sock.send(b'hello server\n')

    with entrypoint(service) as loop:
        loop.run_until_complete(writer())

    assert TestService.DATA
    assert TestService.DATA == [b'hello server\n']
