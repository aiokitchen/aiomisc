import asyncio
import os
import pickle
import socket
import uuid
from asyncio import Event, get_event_loop
from asyncio.tasks import Task
from contextlib import ExitStack, suppress
from tempfile import mktemp
from types import ModuleType
from typing import Any, Optional, Set, Tuple
from unittest import mock

import aiohttp.web
import fastapi
import grpc.aio
import pytest

import aiomisc
from aiomisc import timeout
from aiomisc.entrypoint import Entrypoint, entrypoint
from aiomisc.service import TCPServer, TLSServer, UDPServer
from aiomisc.service.aiohttp import AIOHTTPService
from aiomisc.service.asgi import ASGIApplicationType, ASGIHTTPService
from aiomisc.service.grpc_server import GRPCService
from aiomisc.service.tcp import RobustTCPClient, TCPClient
from aiomisc.service.tls import RobustTLSClient, TLSClient
from aiomisc.service.uvicorn import UvicornApplication, UvicornService
from aiomisc_log import LogFormat
from aiomisc_log.enum import DateFormat, LogLevel
from tests import unix_only

try:
    import uvloop

    uvloop_loop_type = uvloop.Loop
except ImportError:
    uvloop_loop_type = None  # type: ignore


pytestmark = pytest.mark.catch_loop_exceptions


@pytest.fixture()
def unix_socket_udp():
    socket_path = mktemp(dir="/tmp", suffix=".sock")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    sock.setblocking(False)

    # Behaviour like in the bind_socket
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    try:
        sock.bind(socket_path)
        yield sock
    except Exception:
        pass
    else:
        sock.close()
    finally:
        if os.path.exists(socket_path):
            os.remove(socket_path)


@pytest.fixture()
def unix_socket_tcp():
    socket_path = mktemp(dir="/tmp", suffix=".sock")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.setblocking(False)

    try:
        sock.bind(socket_path)
        yield sock
    except Exception:
        pass
    else:
        sock.close()
    finally:
        if os.path.exists(socket_path):
            os.remove(socket_path)


def test_service_class():
    with pytest.raises(TypeError):
        service = aiomisc.Service(running=False, stopped=False)  # type: ignore
        with aiomisc.entrypoint(service):
            pass


def test_simple():
    class StartingService(aiomisc.Service):
        async def start(self):
            self.running = True

    class DummyService(StartingService):
        async def stop(self, err: Exception | None = None):
            self.stopped = True

    services: tuple[StartingService, ...]
    dummy_services: tuple[DummyService, ...]

    dummy_services = (
        DummyService(running=False, stopped=False),
        DummyService(running=False, stopped=False),
    )

    with aiomisc.entrypoint(*dummy_services):
        pass

    for svc in dummy_services:
        assert svc.running
        assert svc.stopped

    dummy_services = (
        DummyService(running=False, stopped=False),
        DummyService(running=False, stopped=False),
    )

    with pytest.raises(RuntimeError):
        with aiomisc.entrypoint(*dummy_services):
            raise RuntimeError

    for svc in dummy_services:
        assert svc.running
        assert svc.stopped

    services = (StartingService(running=False), StartingService(running=False))

    with pytest.raises(RuntimeError):
        with aiomisc.entrypoint(*services):
            raise RuntimeError

    for starting_svc in services:
        assert starting_svc.running


def test_wrong_subclass():
    with pytest.raises(TypeError):

        class NoAsyncStartService(aiomisc.Service):
            def start(self):
                return True

    class MyService(aiomisc.Service):
        async def start(self):
            return

    with pytest.raises(TypeError):

        class NoAsyncStopServiceSubclass(MyService):
            def stop(self, *_) -> Any:
                return True

    class AsyncStopServiceSubclass(MyService):
        async def stop(self, *_) -> Any:
            return True


def test_required_kwargs():
    class Svc(aiomisc.Service):
        __required__ = ("foo",)

        async def start(self):
            pass

    with pytest.raises(AttributeError):
        Svc()

    assert Svc(foo="bar").foo == "bar"


def test_tcp_server():
    event = asyncio.Event()

    class TestService(TCPServer):
        DATA = []

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            writer.close()
            event.set()

    service = TestService("127.0.0.1", 0)

    @aiomisc.threaded
    def writer(port):
        with socket.create_connection(("127.0.0.1", port)) as sock:
            sock.send(b"hello server\n")

    with aiomisc.entrypoint(service) as loop:
        loop.run_until_complete(
            asyncio.wait_for(writer(service.port), timeout=10)
        )
        loop.run_until_complete(event.wait())

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


def test_tcp_client(aiomisc_socket_factory, localhost):
    event = asyncio.Event()

    class TestService(TCPServer):
        DATA = []

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            event.set()

    class TestClient(TCPClient):
        async def handle_connection(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            writer.write(b"hello server\n")
            await writer.drain()

    port, sock = aiomisc_socket_factory()
    event = asyncio.Event()
    services = [
        TestService(sock=sock),
        TestClient(address=localhost, port=port),
    ]

    async def go():
        await event.wait()

    with aiomisc.entrypoint(*services) as loop:
        loop.run_until_complete(asyncio.wait_for(go(), timeout=10))
        loop.run_until_complete(event.wait())

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


async def test_robust_tcp_client(event_loop, aiomisc_socket_factory, localhost):
    condition = asyncio.Condition()

    class TestService(TCPServer):
        DATA = []
        condition: asyncio.Condition

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            async with self.condition:
                self.condition.notify_all()
            writer.write_eof()
            writer.close()

    class TestClient(RobustTCPClient):
        async def handle_connection(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            writer.write(b"hello server\n")
            await writer.drain()
            await reader.readexactly(1)

    port, sock = aiomisc_socket_factory()
    services = [
        TestService(sock=sock, condition=condition),
        TestClient(address=localhost, port=port, reconnect_timeout=0.1),
    ]

    async def go():
        async with condition:
            await condition.wait_for(lambda: len(TestService.DATA) >= 3)

    async with aiomisc.entrypoint(*services):
        await asyncio.wait_for(go(), timeout=10)

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"] * 3


@pytest.mark.parametrize("client_cert_required", [False, True])
def test_tls_server(client_cert_required, certs, ssl_client_context, localhost):
    class TestService(TLSServer):
        DATA = []
        event: asyncio.Event

        async def start(self):
            await super().start()
            self.event = asyncio.Event()

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            print("handle_client")
            self.DATA.append(await reader.readline())
            writer.close()
            self.event.set()

    service = TestService(
        address="127.0.0.1",
        port=0,
        ca=certs / "ca.pem",
        key=certs / "server.key",
        cert=certs / "server.pem",
        require_client_cert=client_cert_required,
    )

    @aiomisc.threaded
    def writer(port):
        with ExitStack() as stack:
            sock = stack.enter_context(
                socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
            )

            ssock = stack.enter_context(
                ssl_client_context.wrap_socket(
                    sock, server_hostname="localhost"
                )
            )

            ssock.connect(("127.0.0.1", port))
            count_bytes = ssock.send(b"hello server\n")
            assert count_bytes == len(b"hello server\n")

    @timeout(999)
    async def go():
        await asyncio.wait_for(writer(service.port), timeout=10)
        await service.event.wait()

    with aiomisc.entrypoint(service) as loop:
        assert service.address == localhost
        loop.run_until_complete(go())

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


async def test_tls_client(event_loop, certs, localhost, aiomisc_socket_factory):
    class TestService(TLSServer):
        DATA = []

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            writer.close()

    class TestClient(TLSClient):
        event: asyncio.Event

        async def handle_connection(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            writer.write(b"hello server\n")
            await writer.drain()
            self.event.set()

    event = asyncio.Event()
    port, sock = aiomisc_socket_factory()
    services = [
        TestService(
            sock=sock,
            ca=certs / "ca.pem",
            key=certs / "server.key",
            cert=certs / "server.pem",
        ),
        TestClient(
            address=localhost,
            port=port,
            ca=certs / "ca.pem",
            key=certs / "client.key",
            cert=certs / "client.pem",
            event=event,
        ),
    ]

    async def go():
        await event.wait()

    async with aiomisc.entrypoint(*services):
        await asyncio.wait_for(go(), timeout=10)

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


async def test_robust_tls_client(
    event_loop, aiomisc_socket_factory, localhost, certs
):
    condition = asyncio.Condition()

    class TestService(TLSServer):
        DATA = []
        condition: asyncio.Condition

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            async with self.condition:
                self.condition.notify_all()
            writer.close()

    class TestClient(RobustTLSClient):
        async def handle_connection(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            writer.write(b"hello server\n")
            await writer.drain()
            await reader.readexactly(1)

    port, sock = aiomisc_socket_factory()
    services = [
        TestService(
            sock=sock,
            ca=certs / "ca.pem",
            key=certs / "server.key",
            cert=certs / "server.pem",
            condition=condition,
        ),
        TestClient(
            address=localhost,
            port=port,
            ca=certs / "ca.pem",
            key=certs / "client.key",
            cert=certs / "client.pem",
            reconnect_timeout=0.1,
        ),
    ]

    async def go():
        async with condition:
            await condition.wait_for(lambda: len(TestService.DATA) >= 3)

    async with aiomisc.entrypoint(*services):
        await asyncio.wait_for(go(), timeout=10)

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"] * 3


def test_udp_server(aiomisc_socket_factory):
    port, sock = aiomisc_socket_factory(socket.AF_INET, socket.SOCK_DGRAM)

    event = asyncio.Event()

    class TestService(UDPServer):
        DATA = []

        async def handle_datagram(self, data: bytes, addr: tuple) -> None:
            self.DATA.append(data)
            event.set()

    service = TestService("127.0.0.1", sock=sock)

    @aiomisc.threaded
    def writer():
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        with sock:
            sock.sendto(b"hello server\n", ("127.0.0.1", port))

    with aiomisc.entrypoint(service) as loop:
        loop.run_until_complete(asyncio.wait_for(writer(), timeout=10))
        loop.run_until_complete(event.wait())

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


def test_udp_without_port_or_socket():
    class TestService(UDPServer):
        async def handle_datagram(self, data: bytes, addr: tuple) -> None:
            pass

    with pytest.raises(RuntimeError):
        TestService()


def test_tcp_without_port_or_socket():
    class TestService(TCPServer):
        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> Any:
            pass

    with pytest.raises(RuntimeError):
        TestService()


@unix_only
def test_udp_socket_server(unix_socket_udp):
    class TestService(UDPServer):
        DATA = []

        async def handle_datagram(self, data: bytes, addr: tuple):
            self.DATA.append(data)

    service = TestService(sock=unix_socket_udp)

    @aiomisc.threaded
    def writer():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)

        with sock:
            sock.sendto(b"hello server\n", unix_socket_udp.getsockname())

    with aiomisc.entrypoint(service) as loop:
        loop.run_until_complete(asyncio.wait_for(writer(), timeout=10))

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


@unix_only
def test_tcp_server_unix(unix_socket_tcp):
    class TestService(TCPServer):
        DATA = []

        async def handle_client(
            self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ):
            self.DATA.append(await reader.readline())
            writer.close()

    service = TestService(sock=unix_socket_tcp)

    @aiomisc.threaded
    def writer():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(unix_socket_tcp.getsockname())
            sock.send(b"hello server\n")

    with aiomisc.entrypoint(service) as loop:
        loop.run_until_complete(asyncio.wait_for(writer(), timeout=10))

    assert TestService.DATA
    assert TestService.DATA == [b"hello server\n"]


def test_aiohttp_service_create_app():
    with pytest.raises(TypeError):

        class NoAsyncCreateApplication(AIOHTTPService):
            def create_application(self):
                return None

    class AsyncCreateApplication(AIOHTTPService):
        async def create_application(self):
            return aiohttp.web.Application()


class AIOHTTPTestApp(AIOHTTPService):
    async def create_application(self):
        return aiohttp.web.Application()


def test_aiohttp_service(aiomisc_unused_port):
    async def http_client():
        session = aiohttp.ClientSession()
        url = f"http://localhost:{aiomisc_unused_port}"

        async with session:
            async with session.get(url) as response:
                return response.status

    service = AIOHTTPTestApp(address="127.0.0.1", port=aiomisc_unused_port)

    with aiomisc.entrypoint(service) as loop:
        response = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10)
        )

    assert response == 404


@unix_only
def test_aiohttp_service_sock(unix_socket_tcp):
    async def http_client():
        conn = aiohttp.UnixConnector(path=unix_socket_tcp.getsockname())
        session = aiohttp.ClientSession(connector=conn)

        async with session:
            async with session.get("http://unix/") as response:
                return response.status

    service = AIOHTTPTestApp(sock=unix_socket_tcp)

    with aiomisc.entrypoint(service) as loop:
        response = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10000)
        )

    assert response == 404


def test_asgi_service_create_app():
    with pytest.raises(TypeError):

        class NoAsyncCreateASGIApp(ASGIHTTPService):
            def create_asgi_app(self) -> ASGIApplicationType:  # type: ignore
                return lambda: None  # type: ignore

    class AsyncCreateASGIApp(ASGIHTTPService):
        async def create_asgi_app(self) -> ASGIApplicationType:
            return fastapi.FastAPI()


class ASGIHTTPTestApp(ASGIHTTPService):
    async def create_asgi_app(self) -> ASGIApplicationType:
        app = fastapi.FastAPI()

        @app.get("/")
        async def root():
            return {"message": "Hello World"}

        return app


def test_aiohttp_service_without_port_or_sock(aiomisc_unused_port):
    with pytest.raises(RuntimeError):
        ASGIHTTPTestApp()


def test_asgi_service(aiomisc_unused_port):
    async def http_client():
        session = aiohttp.ClientSession()
        url = f"http://localhost:{aiomisc_unused_port}"

        async with session:
            async with session.get(url) as response:
                return response.status, await response.json()

    service = ASGIHTTPTestApp(address="127.0.0.1", port=aiomisc_unused_port)

    with aiomisc.entrypoint(service) as loop:
        response, body = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10)
        )

    assert body == {"message": "Hello World"}
    assert response == 200


@unix_only
def test_asgi_service_sock(unix_socket_tcp):
    async def http_client():
        conn = aiohttp.UnixConnector(path=unix_socket_tcp.getsockname())
        session = aiohttp.ClientSession(connector=conn)

        async with session:
            async with session.get("http://unix/") as response:
                return response.status, await response.json()

    service = ASGIHTTPTestApp(sock=unix_socket_tcp)

    with aiomisc.entrypoint(service) as loop:
        response, body = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10000)
        )

    assert body == {"message": "Hello World"}
    assert response == 200


class UvicornTestService(UvicornService):
    async def create_application(self) -> UvicornApplication:
        app = fastapi.FastAPI()

        @app.get("/")
        async def root():
            return {"message": "Hello World"}

        return app


def test_uvicorn_service(aiomisc_unused_port):
    async def http_client():
        session = aiohttp.ClientSession()
        url = f"http://localhost:{aiomisc_unused_port}"

        async with session:
            async with session.get(url) as response:
                return response.status, await response.json()

    service = UvicornTestService(host="127.0.0.1", port=aiomisc_unused_port)

    with aiomisc.entrypoint(service) as loop:
        response, body = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10)
        )

    assert body == {"message": "Hello World"}
    assert response == 200


@unix_only
def test_uvicorn_service_sock(unix_socket_tcp):
    async def http_client():
        conn = aiohttp.UnixConnector(path=unix_socket_tcp.getsockname())
        session = aiohttp.ClientSession(connector=conn)

        async with session:
            async with session.get("http://unix/") as response:
                return response.status, await response.json()

    service = UvicornTestService(sock=unix_socket_tcp)

    with aiomisc.entrypoint(service) as loop:
        response, body = loop.run_until_complete(
            asyncio.wait_for(http_client(), timeout=10000)
        )

    assert body == {"message": "Hello World"}
    assert response == 200


def test_service_events():
    class Initialization(aiomisc.Service):
        async def start(self):
            context = aiomisc.get_context()
            await asyncio.sleep(0.1)
            context["test"] = True

    class Awaiter(aiomisc.Service):
        result = None

        async def start(self):
            Awaiter.result = await self.context["test"]

    services = (Awaiter(), Initialization())

    with aiomisc.entrypoint(*services):
        pass

    assert Awaiter.result


def test_service_events_2():
    class Initialization(aiomisc.Service):
        async def start(self):
            self.context["test"] = True

    class Awaiter(aiomisc.Service):
        result = None

        async def start(self):
            context = aiomisc.get_context()

            await asyncio.sleep(0.1)

            await context["test"]
            Awaiter.result = await context["test"]

    services = (Initialization(), Awaiter())

    with aiomisc.entrypoint(*services):
        pass

    assert Awaiter.result


def test_service_start_event():
    class Sleeper(aiomisc.Service):
        result = False

        async def start(self):
            self.start_event.set()

            await asyncio.sleep(86400)
            Sleeper.result = True

    with aiomisc.entrypoint(Sleeper()):
        pass

    assert not Sleeper.result


def test_service_no_start_event():
    class Sleeper(aiomisc.Service):
        result = False

        async def start(self):
            await asyncio.sleep(1)
            Sleeper.result = True

    with aiomisc.entrypoint(Sleeper()):
        pass

    assert Sleeper.result


def test_context_multiple_set():
    results = []

    async def test():
        context = aiomisc.get_context()

        context["foo"] = True
        await asyncio.sleep(0.1)
        results.append(await context["foo"])

        context["foo"] = False
        await asyncio.sleep(0.1)
        results.append(await context["foo"])

        context["foo"] = None
        await asyncio.sleep(0.1)
        results.append(await context["foo"])

    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(asyncio.wait_for(test(), timeout=10))

    assert results == [True, False, None]


async def test_entrypoint_with_with_async():
    class MyService(aiomisc.service.Service):
        ctx = 0

        async def start(self):
            self.__class__.ctx = 1

        async def stop(self, exc: Exception | None = None) -> None:
            self.__class__.ctx = 2

    service = MyService()
    assert service.ctx == 0

    async with aiomisc.entrypoint(service) as ep:
        assert service.ctx == 1

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ep.closing(), timeout=0.3)

        assert service.ctx == 1

    assert service.ctx == 2


async def test_entrypoint_graceful_shutdown_loop_owner(event_loop):
    event = Event()
    task: Task

    async def func():
        nonlocal event
        await event.wait()

    async def pre_start(**_):
        nonlocal task
        task = get_event_loop().create_task(func())

    async def post_stop(**_):
        nonlocal event, task
        event.set()
        with suppress(asyncio.TimeoutError):
            await asyncio.wait_for(task, timeout=1.0)

    Entrypoint.PRE_START.connect(pre_start)
    Entrypoint.POST_STOP.connect(post_stop)

    async with Entrypoint() as entrypoint:
        assert entrypoint.loop is event_loop

    Entrypoint.PRE_START.disconnect(pre_start)
    Entrypoint.POST_STOP.disconnect(post_stop)

    assert task.done()
    assert not task.cancelled()


class CucumberService(aiomisc.Service):
    async def start(self) -> None:
        return


async def test_service_pickle():
    cucumbers = [CucumberService(index=i) for i in range(100)]
    pickled_cucumbers = pickle.dumps(cucumbers)

    cucumbers.clear()

    for idx, cucumber in enumerate(pickle.loads(pickled_cucumbers)):
        assert cucumber.index == idx


class StorageService(aiomisc.Service):
    INSTANCES: set["StorageService"] = set()

    async def start(self) -> None:
        self.INSTANCES.add(self)

    async def stop(self, exc: Exception | None = None) -> None:
        self.INSTANCES.remove(self)


async def test_add_remove_service(entrypoint: aiomisc.Entrypoint):
    StorageService.INSTANCES.clear()

    service = StorageService()

    await entrypoint.start_services(service)
    assert len(StorageService.INSTANCES) == 1
    assert service in StorageService.INSTANCES

    await entrypoint.stop_services(service)
    assert service not in StorageService.INSTANCES

    assert len(StorageService.INSTANCES) == 0

    for service in map(lambda _: StorageService(), range(10)):
        await entrypoint.start_services(service)

    assert len(StorageService.INSTANCES) == 10


@pytest.mark.parametrize(
    "entrypoint_logging_kwargs,basic_config_kwargs",
    [
        (
            {
                "log_level": LogLevel.info.name,
                "log_format": LogFormat.plain,
                "log_date_format": None,
            },
            {
                "level": LogLevel.info.name,
                "log_format": LogFormat.plain,
                "date_format": None,
            },
        ),
        (
            {
                "log_level": LogLevel.debug,
                "log_format": LogFormat.stream,
                "log_date_format": DateFormat.stream,
            },
            {
                "level": LogLevel.debug,
                "log_format": LogFormat.stream,
                "date_format": DateFormat.stream,
            },
        ),
    ],
)
def test_entrypoint_log_params(entrypoint_logging_kwargs, basic_config_kwargs):
    with mock.patch("aiomisc_log.basic_config") as basic_config_mock:
        with entrypoint(**entrypoint_logging_kwargs):
            pass

        # unbuffered logging is configured on init, buffered on start,
        # unbuffered on stop.
        assert basic_config_mock.call_count == 3
        for call_args, call_kwargs in basic_config_mock.call_args_list:
            for key, value in basic_config_kwargs.items():
                assert call_kwargs[key] == value


@pytest.fixture(scope="session")
def grpc_hello() -> tuple[ModuleType, ModuleType]:
    return grpc.protos_and_services("tests/hello.proto")


def test_grpc_service(localhost, grpc_hello):
    protos, services = grpc_hello
    token = uuid.uuid4().hex

    class Greeter(services.GreeterServicer):  # type: ignore
        async def SayHello(self, request, context):
            return protos.HelloReply(message=f"{request.name}")

    grpc_service = GRPCService(compression=grpc.Compression.Gzip)
    services.add_GreeterServicer_to_server(Greeter(), grpc_service)

    port_future = grpc_service.add_insecure_port(f"{localhost}:0")

    async def go():
        port: int = await port_future

        async with grpc.aio.insecure_channel(f"{localhost}:{port}") as channel:
            stub = services.GreeterStub(channel)
            response = await stub.SayHello(protos.HelloRequest(name=token))

        return response.message

    with aiomisc.entrypoint(grpc_service) as loop:
        result = loop.run_until_complete(go())

    assert result == token
