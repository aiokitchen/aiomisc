import asyncio
import logging
import os
import socket
import sys
from asyncio.events import get_event_loop
from contextlib import contextmanager, suppress
from functools import partial, wraps
from inspect import isasyncgenfunction
from typing import Callable, Coroutine, NamedTuple, Optional, Tuple, Type, Union
from unittest.mock import MagicMock

import pytest

import aiomisc
from aiomisc.utils import bind_socket
from aiomisc_log import LOG_LEVEL, basic_config


log = logging.getLogger("aiomisc_pytest")
asyncio.get_event_loop = MagicMock(asyncio.get_event_loop)
asyncio.get_event_loop.side_effect = get_event_loop


try:
    import uvloop  # type: ignore
except ImportError:
    uvloop = None


def delayed_future(
    timeout: Union[int, float], result: bool = True,
) -> asyncio.Future:

    loop = asyncio.get_event_loop()

    def resolve(f: asyncio.Future) -> None:
        nonlocal result

        if f.done():
            return
        f.set_result(result)

    future = loop.create_future()
    handle = loop.call_later(timeout, resolve, future)
    future.add_done_callback(lambda _: handle.cancel())

    return future


ProxyProcessorType = Coroutine[bytes, None, bytes]
DelayType = Union[int, float]


class Delay:
    __slots__ = "__timeout", "future", "lock"

    def __init__(self) -> None:
        self.__timeout: Union[int, float] = 0
        self.future = None
        self.lock = asyncio.Lock()

    @property
    def timeout(self) -> Union[int, float]:
        return self.__timeout

    @timeout.setter
    def timeout(self, value: DelayType):
        assert isinstance(value, (int, float))
        assert value >= 0

        self.__timeout = value

        if self.future and not self.future.done():
            self.future.set_result(True)

    async def wait(self):
        if self.__timeout == 0:
            return

        async with self.lock:
            try:
                self.future = delayed_future(self.__timeout)
                await self.future
            finally:
                self.future = None


class TCPProxyClient:
    __slots__ = (
        "client_reader", "client_writer",
        "server_reader", "server_writer",
        "chunk_size", "tasks", "loop",
        "read_delay", "write_delay", "closing",
        "__processors", "__client_repr", "__server_repr",
        "buffered",
    )

    @staticmethod
    async def _blank_processor(body: bytes) -> bytes:
        return body

    def __init__(
        self, client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        chunk_size: int = 64 * 1024, buffered: bool = False,
    ):

        self.loop = asyncio.get_event_loop()
        self.client_reader = client_reader  # type: asyncio.StreamReader
        self.client_writer = client_writer  # type: asyncio.StreamWriter

        self.server_reader = None  # type: t.Optional[asyncio.StreamReader]
        self.server_writer = None  # type: t.Optional[asyncio.StreamWriter]

        self.tasks = ()  # type: t.Iterable[asyncio.Task]
        self.chunk_size = chunk_size  # type: int
        self.read_delay = Delay()
        self.write_delay = Delay()

        self.closing = self.loop.create_future()  # type: asyncio.Future
        self.__processors = {
            "read": self._blank_processor,
            "write": self._blank_processor,
        }  # type: t.Dict[str, t.Callable[[], ProxyProcessorType]]

        self.buffered = bool(buffered)

        self.__client_repr = None
        self.__server_repr = None

    @property
    def read_processor(self) -> Callable[[], ProxyProcessorType]:
        return self.__processors["read"]

    @read_processor.setter
    def read_processor(self, value: Optional[ProxyProcessorType]) -> None:
        if value is None:
            self.__processors["read"] = self._blank_processor
            return

        self.__processors["read"] = aiomisc.awaitable(value)

    @property
    def write_processor(self) -> Callable[[], ProxyProcessorType]:
        return self.__processors["write"]

    @write_processor.setter
    def write_processor(self, value: Optional[ProxyProcessorType]) -> None:
        if value is None:
            self.__processors["write"] = self._blank_processor
            return
        self.__processors["write"] = aiomisc.awaitable(value)

    def __repr__(self):
        return "<%s[%x]: %s => %s>" % (
            self.__class__.__name__, id(self),
            self.__client_repr, self.__server_repr,
        )

    if sys.version_info < (3, 7):
        @staticmethod
        async def _close_writer(writer: asyncio.StreamWriter):
            writer.close()
    else:
        @staticmethod
        async def _close_writer(writer: asyncio.StreamWriter):
            writer.close()
            await writer.wait_closed()

    async def pipe(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        processor: str,
        delay: Delay,
    ) -> None:
        try:
            while not reader.at_eof():
                chunk = await reader.read(self.chunk_size)

                if delay.timeout > 0:
                    log.debug(
                        "%r sleeping %.3f seconds on %s",
                        self, delay.timeout, processor,
                    )

                await delay.wait()

                writer.write(await self.__processors[processor](chunk))

                if not self.buffered:
                    await writer.drain()
        finally:
            await self._close_writer(writer)

    async def connect(self, target_host: str, target_port: int) -> None:
        log.debug("Establishing connection for %r", self)

        self.server_reader, self.server_writer = await asyncio.open_connection(
            host=target_host, port=target_port,
        )

        self.__client_repr = ":".join(
            map(str, self.client_writer.get_extra_info("peername")[:2]),
        )
        self.__server_repr = ":".join(
            map(str, self.server_writer.get_extra_info("peername")[:2]),
        )

        self.tasks = (
            self.loop.create_task(
                self.pipe(
                    self.server_reader,
                    self.client_writer,
                    "write",
                    self.write_delay,
                ),
            ),
            self.loop.create_task(
                self.pipe(
                    self.client_reader,
                    self.server_writer,
                    "read",
                    self.read_delay,
                ),
            ),
        )

    async def close(self):
        log.debug("Closing %r", self)
        if self.closing.done():
            return

        await aiomisc.cancel_tasks(self.tasks)
        self.loop.call_soon(self.closing.set_result, True)
        await self.closing


class TCPProxy:
    DEFAULT_TIMEOUT = 30

    __slots__ = (
        "proxy_port", "clients", "server", "proxy_host",
        "target_port", "target_host", "listen_host", "read_delay",
        "write_delay", "read_processor", "write_processor", "buffered",
    )

    def __init__(
            self, target_host: str, target_port: int,
            listen_host: str = "127.0.0.1", buffered: bool = True,
    ):
        self.target_port = target_port
        self.target_host = target_host
        self.proxy_host = listen_host
        self.proxy_port = get_unused_port()
        self.read_delay = 0
        self.write_delay = 0
        self.buffered = buffered

        self.clients = set()  # type: t.Set[TCPProxyClient]
        self.server = None  # type: t.Optional[asyncio.AbstractServer]

        self.read_processor = None  # type: t.Optional[ProxyProcessorType]
        self.write_processor = None  # type: t.Optional[ProxyProcessorType]

    def __repr__(self):
        return "<%s[%x]: tcp://%s:%s => tcp://%s:%s>" % (
            self.__class__.__name__, id(self),
            self.proxy_host, self.proxy_port,
            self.target_host, self.target_port,
        )

    async def start(self, timeout=None) -> asyncio.AbstractServer:
        log.debug("Starting %r", self)
        self.server = await asyncio.wait_for(
            asyncio.start_server(
                self._handle_client,
                host=self.proxy_host,
                port=self.proxy_port,
            ), timeout=timeout,
        )
        return self.server

    ClientType = Tuple[asyncio.StreamReader, asyncio.StreamWriter]

    async def create_client(self) -> ClientType:
        log.debug("Creating client for %r", self)
        return await asyncio.open_connection(
            self.proxy_host, self.proxy_port,
        )

    async def __aenter__(self):
        if self.server is None:
            await self.start(timeout=self.DEFAULT_TIMEOUT)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close(timeout=self.DEFAULT_TIMEOUT)

    async def close(self, timeout=None):
        async def close():
            await self.disconnect_all()
            self.server.close()
            await self.server.wait_closed()
        await asyncio.wait_for(close(), timeout=timeout)

    def set_delay(self, read_delay: DelayType, write_delay: DelayType = 0):
        log.debug("Setting delay [R/W %f %f]", read_delay, write_delay)

        for client in self.clients:
            log.debug(
                "Applying delays [R/W: %f %f] for %r",
                read_delay, write_delay, client,
            )
            client.read_delay.timeout = read_delay
            client.write_delay.timeout = write_delay

        self.read_delay = read_delay
        self.write_delay = write_delay

    def set_content_processors(
            self, read: Optional[ProxyProcessorType],
            write: Optional[ProxyProcessorType],
    ):
        log.debug(
            "Setting content processors for %r: read=%r write=%r",
            self, read, write,
        )
        for client in self.clients:
            log.debug(
                "Applying context processors for %r: read=%r write=%r",
                client, read, write,
            )
            client.read_processor = read
            client.write_processor = write

        self.read_processor = read
        self.write_processor = write

    def disconnect_all(self) -> asyncio.Future:
        log.debug(
            "Disconnecting %s clients of %r", len(self.clients), self,
        )
        return asyncio.ensure_future(
            asyncio.gather(
                *[client.close() for client in self.clients],
                return_exceptions=True
            ),
        )

    async def _handle_client(
            self, reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
    ):
        client = TCPProxyClient(reader, writer, buffered=self.buffered)
        self.clients.add(client)

        client.read_delay.timeout = self.read_delay
        client.write_delay.timeout = self.write_delay
        client.read_processor = self.read_processor
        client.write_processor = self.write_processor

        await client.connect(self.target_host, self.target_port)

        client.closing.add_done_callback(
            lambda _: self.clients.remove(client),
        )

    @contextmanager
    def slowdown(self, read_delay: DelayType = 0, write_delay: DelayType = 0):
        old_read_delay = self.read_delay
        old_write_delay = self.write_delay

        self.set_delay(read_delay, write_delay)

        try:
            yield
        finally:
            self.set_delay(old_read_delay, old_write_delay)


@pytest.fixture(scope="session")
def tcp_proxy() -> Type[TCPProxy]:
    return TCPProxy


def isasyncgenerator(func):
    if isasyncgenfunction(func):
        return True
    elif asyncio.iscoroutinefunction(func):
        return False


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "forbid_get_event_loop: "
        "fail when asyncio.get_event_loop will be called",
    )
    config.addinivalue_line(
        "markers",
        "catch_loop_exceptions: "
        "fails when unhandled loop exception "
        "will be raised",
    )


def pytest_addoption(parser):
    group = parser.getgroup("aiomisc plugin options")
    group.addoption(
        "--aiomisc", action="store_true", default=True,
        help="Use aiomisc entrypoint for run async tests",
    )

    group.addoption(
        "--aiomisc-debug", action="store_true", default=False,
        help="Set debug for event loop",
    )

    group.addoption(
        "--aiomisc-pool-size", type=int, default=4,
        help="Default thread pool size",
    )

    group.addoption(
        "--aiomisc-test-timeout", type=float, default=None,
        help="Test timeout",
    )


def pytest_fixture_setup(fixturedef):  # type: ignore
    func = fixturedef.func

    is_async_gen = isasyncgenerator(func)

    if is_async_gen is None:
        return

    strip_request = False
    if "request" not in fixturedef.argnames:
        fixturedef.argnames += ("request",)
        strip_request = True

    def wrapper(*args, **kwargs):  # type: ignore
        if strip_request:
            request = kwargs.pop("request")
        else:
            request = kwargs["request"]

        if "loop" not in request.fixturenames:
            raise Exception("`loop` fixture required")

        event_loop = request.getfixturevalue("loop")

        if not is_async_gen:
            return event_loop.run_until_complete(func(*args, **kwargs))

        gen = func(*args, **kwargs)

        def finalizer():  # type: ignore
            try:
                return event_loop.run_until_complete(gen.__anext__())
            except StopAsyncIteration:  # NOQA
                pass

        request.addfinalizer(finalizer)
        return event_loop.run_until_complete(gen.__anext__())

    fixturedef.func = wrapper


@pytest.fixture(scope="session")
def localhost():
    params = (
        (socket.AF_INET, "127.0.0.1"),
        (socket.AF_INET6, "::1"),
    )
    for family, addr in params:
        with socket.socket(family, socket.SOCK_STREAM) as sock:
            try:
                sock.bind((addr, 0))
            except Exception:
                pass
            else:
                return addr
    raise RuntimeError("localhost unavailable")


@pytest.fixture(autouse=True)
def loop_debug(request):
    return request.config.getoption("--aiomisc-debug")


@pytest.fixture(autouse=True)
def aiomisc_test_timeout(request):
    return request.config.getoption("--aiomisc-test-timeout")


@pytest.fixture(autouse=True)
def aiomisc_func_wrap():
    return aiomisc.awaitable


def pytest_pycollect_makeitem(collector, name, obj):  # type: ignore
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):  # type: ignore
    if not asyncio.iscoroutinefunction(pyfuncitem.function):
        return

    event_loop = pyfuncitem.funcargs.get("loop", None)
    func_wraper = pyfuncitem.funcargs.get(
        "aiomisc_func_wrap", aiomisc.awaitable,
    )

    aiomisc_test_timeout = pyfuncitem.funcargs.get(
        "aiomisc_test_timeout", None,
    )

    kwargs = {
        arg: pyfuncitem.funcargs[arg]
        for arg in pyfuncitem._fixtureinfo.argnames
    }

    @wraps(pyfuncitem.obj)
    async def func():
        return await asyncio.wait_for(
            func_wraper(pyfuncitem.obj)(**kwargs),
            timeout=aiomisc_test_timeout,
        )

    event_loop.run_until_complete(func())

    return True


@pytest.fixture(scope="session")
def thread_pool_size(request):
    return request.config.getoption("--aiomisc-pool-size")


@pytest.fixture
def services():
    return []


@pytest.fixture
def default_context():
    return {}


loop_autouse = os.getenv("AIOMISC_LOOP_AUTOUSE", "1") == "1"


@pytest.fixture
def thread_pool_executor():
    from aiomisc.thread_pool import ThreadPoolExecutor
    return ThreadPoolExecutor


@pytest.fixture(autouse=loop_autouse)
def event_loop_policy():
    if uvloop:
        return uvloop.EventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
def entrypoint_kwargs() -> dict:
    return {"log_config": False}


@pytest.fixture(name="loop", autouse=loop_autouse)
def _loop(event_loop_policy, caplog: pytest.LogCaptureFixture):
    basic_config(
        log_format="plain",
        stream=caplog.handler.stream,
    )

    try:
        asyncio.set_event_loop_policy(event_loop_policy)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            yield loop
        finally:
            basic_config(
                log_format="plain",
                stream=sys.stderr,
            )

            if loop.is_closed():
                return

            with suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            with suppress(Exception):
                loop.close()
    finally:
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())


@pytest.fixture(autouse=loop_autouse)
def loop(
    request, services, loop_debug, default_context, entrypoint_kwargs,
    thread_pool_size, thread_pool_executor, loop, caplog,
):
    from aiomisc.context import get_context
    from aiomisc.entrypoint import entrypoint

    if LOG_LEVEL:
        LOG_LEVEL.set(logging.getLogger().getEffectiveLevel())

    pool = thread_pool_executor(thread_pool_size)
    loop.set_default_executor(pool)

    get_marker = request.node.get_closest_marker
    forbid_loop_getter_marker = get_marker("forbid_get_event_loop")
    catch_unhandled_marker = get_marker("catch_loop_exceptions")

    exceptions = list()
    if catch_unhandled_marker:
        loop.set_exception_handler(lambda l, c: exceptions.append(c))

    try:
        with entrypoint(*services, loop=loop, **entrypoint_kwargs):

            ctx = get_context(loop)

            for key, value in default_context.items():
                ctx[key] = value

            if forbid_loop_getter_marker:
                asyncio.get_event_loop.side_effect = partial(
                    pytest.fail, "get_event_loop is forbidden",
                )

            yield loop

            if exceptions:
                logging.error(
                    "Unhandled exceptions found:\n\n\t%s",
                    "\n\t".join(
                        (
                            "Message: {m}\n\t"
                            "Future: {f}\n\t"
                            "Exception: {e}"
                        ).format(
                            m=e["message"],
                            f=repr(e.get("future")),
                            e=repr(e.get("exception")),
                        ) for e in exceptions
                    ),
                )
                pytest.fail("Unhandled exceptions found. See logs.")
    finally:
        asyncio.get_event_loop.side_effect = get_event_loop
        del loop


def get_unused_port(*args) -> int:
    with socket.socket(*args) as sock:
        sock.bind(("", 0))
        port = sock.getsockname()[1]
    return port


class PortSocket(NamedTuple):
    port: int
    socket: socket.socket


@pytest.fixture
def aiomisc_socket_factory(request, localhost) -> Callable[..., PortSocket]:
    """ Returns a """
    def factory(*args, **kwargs) -> PortSocket:
        sock = bind_socket(*args, address=localhost, port=0, **kwargs)
        port = sock.getsockname()[1]

        # Close socket after teardown
        request.addfinalizer(sock.close)

        return PortSocket(port=port, socket=sock)
    return factory


@pytest.fixture
def aiomisc_unused_port_factory() -> Callable[[], int]:
    return get_unused_port


@pytest.fixture
def aiomisc_unused_port() -> int:
    return get_unused_port()
