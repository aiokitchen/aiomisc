import asyncio
import io
import socket
from threading import Event

from aiomisc import threaded
from aiomisc_worker import protocol


def test_io_protocol(tmp_path):
    with open(tmp_path / "test.bin", "wb") as fp:
        proto = protocol.FileIOProtocol(fp)
        proto.send(("foo", "bar", print))

    with open(tmp_path / "test.bin", "rb") as fp:
        proto = protocol.FileIOProtocol(fp)
        assert proto.receive() == ("foo", "bar", print)


async def test_socket_protocol(localhost, aiomisc_unused_port):
    server_start_event = Event()
    server_data = []
    client_data = []

    @threaded
    def server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((localhost, aiomisc_unused_port))
            sock.listen(1)
            server_start_event.set()
            cs, addr = sock.accept()
            proto = protocol.SocketIOProtocol(cs)
            server_data.append(proto.receive())
            proto.send({"foo": "bar"})

    @threaded
    def client():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            server_start_event.wait(5)
            sock.connect((localhost, aiomisc_unused_port))

            proto = protocol.SocketIOProtocol(sock)
            proto.send({"foo": "bar"})
            client_data.append(proto.receive())

    await asyncio.gather(server(), client())
    assert server_data == [{"foo": "bar"}]
    assert client_data == [{"foo": "bar"}]
    assert server_data == client_data


async def test_socket_protocol_partial_read(localhost, aiomisc_unused_port):
    server_start_event = Event()
    server_data = []
    client_data = []

    @threaded
    def server():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((localhost, aiomisc_unused_port))
            sock.listen(1)
            server_start_event.set()
            cs, addr = sock.accept()
            proto = protocol.SocketIOProtocol(cs)
            data = proto._pack(list(range(10_000)))
            with io.BytesIO(data) as fp:
                chunk = fp.read(1024)
                while chunk:
                    proto.sock.send(chunk)
                    chunk = fp.read(1024)
            server_data.append(proto.receive())

    @threaded
    def client():
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            server_start_event.wait(5)
            sock.connect((localhost, aiomisc_unused_port))

            proto = protocol.SocketIOProtocol(sock)
            data = proto.receive()
            proto.send(len(data))
            client_data.append(data)

    await asyncio.gather(server(), client())
    assert server_data == [10_000]
    assert client_data == [list(range(10_000))]
