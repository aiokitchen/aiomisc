import asyncio
import logging
import os
import socket
import typing as t
from asyncio.events import get_event_loop
from contextlib import suppress
from functools import partial, wraps
from unittest.mock import MagicMock

import pytest

import aiomisc


asyncio.get_event_loop = MagicMock(asyncio.get_event_loop)
asyncio.get_event_loop.side_effect = get_event_loop


try:
    import uvloop
except ImportError:
    uvloop = None


try:
    from async_generator import isasyncgenfunction
except ImportError:
    from inspect import isasyncgenfunction


ProxyProcessorType = t.Callable[[bytes], t.Union[bytes, t.Awaitable[bytes]]]


class TCPProxyClient:
    __slots__ = (
        "client_reader", "client_writer",
        "server_reader", "server_writer",
        "chunk_size", "tasks", "loop",
        "delay", "closing",
        "read_processor", "write_processor",
    )

    def __init__(
        self, client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        chunk_size: int = 64 * 1024,
    ):

        self.loop = asyncio.get_event_loop()
        self.client_reader = client_reader  # type: asyncio.StreamReader
        self.client_writer = client_writer  # type: asyncio.StreamWriter

        self.server_reader = None  # type: t.Optional[asyncio.StreamReader]
        self.server_writer = None  # type: t.Optional[asyncio.StreamWriter]

        self.tasks = ()                     # type: t.Iterable[asyncio.Task]
        self.chunk_size = chunk_size        # type: int
        self.delay = 0
        self.closing = self.loop.create_future()
        self.read_processor = None   # type: t.Optional[ProxyProcessorType]
        self.write_processor = None  # type: t.Optional[ProxyProcessorType]

    async def pipe(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        processor: str
    ) -> None:
        try:
            while True:
                data = await reader.read(self.chunk_size)
                processor_func = getattr(self, processor)

                if not data:
                    return

                if processor_func:
                    data = await aiomisc.awaitable(processor_func)(data)

                if self.delay > 0:
                    await asyncio.sleep(self.delay)

                writer.write(data)
                await writer.drain()
        except asyncio.CancelledError:
            reader.feed_eof()
            raise
        finally:
            writer.close()
            await writer.wait_closed()

    async def connect(self, target_host: str, target_port: int) -> None:
        self.server_reader, self.server_writer = await asyncio.open_connection(
            host=target_host, port=target_port,
        )

        self.tasks = (
            self.loop.create_task(
                self.pipe(
                    self.server_reader,
                    self.client_writer,
                    "write_processor",
                ),
            ),
            self.loop.create_task(
                self.pipe(
                    self.client_reader,
                    self.server_writer,
                    "read_processor",
                ),
            ),
        )

    async def close(self):
        if self.closing.done():
            return

        await aiomisc.cancel_tasks(self.tasks)
        self.loop.call_soon(self.closing.set_result, True)
        await self.closing


class TCPProxy:
    __slots__ = (
        "proxy_port", "clients", "server", "proxy_host",
        "target_port", "target_host", "listen_host", "delay",
        "read_processor", "write_processor",
    )

    def __init__(
        self, target_host: str, target_port: int,
        listen_host: str = "127.0.0.1",
    ):
        self.target_port = target_port
        self.target_host = target_host
        self.proxy_host = listen_host
        self.proxy_port = get_unused_port()
        self.delay = 0

        self.clients = set()        # type: t.Set[TCPProxyClient]
        self.server = None  # type: t.Optional[asyncio.AbstractServer]

        self.read_processor = None    # type: t.Optional[ProxyProcessorType]
        self.write_processor = None  # type: t.Optional[ProxyProcessorType]

    async def start(self, timeout=None) -> asyncio.AbstractServer:
        self.server = await asyncio.wait_for(
            asyncio.start_server(
                self._handle_client,
                host=self.proxy_host,
                port=self.proxy_port,
            ), timeout=timeout,
        )
        return self.server

    async def close(self):
        await self.disconnect_all()
        self.server.close()
        await self.server.wait_closed()

    def set_delay(self, delay: float):
        for client in self.clients:
            client.delay = delay
        self.delay = delay

    def set_content_processors(
        self, read: t.Optional[ProxyProcessorType],
        write: t.Optional[ProxyProcessorType],
    ):
        for client in self.clients:
            client.read_processor = read
            client.write_processor = write

        self.read_processor = read
        self.write_processor = write

    def disconnect_all(self) -> asyncio.Future:
        return asyncio.ensure_future(
            asyncio.gather(
                *[client.close() for client in self.clients],
                return_exceptions=True
            ),
        )

    async def _handle_client(
        self, reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter
    ):
        client = TCPProxyClient(reader, writer)
        self.clients.add(client)

        client.delay = self.delay
        client.read_processor = self.read_processor
        client.write_processor = self.write_processor

        await client.connect(self.target_host, self.target_port)

        client.closing.add_done_callback(
            lambda _: self.clients.remove(client),
        )


@pytest.fixture(scope="session")
def tcp_proxy() -> t.Type[TCPProxy]:
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


@pytest.fixture
def loop_debug(request):
    return request.config.getoption("--aiomisc-debug")


@pytest.fixture
def aiomisc_test_timeout(request):
    return request.config.getoption("--aiomisc-test-timeout")


def pytest_pycollect_makeitem(collector, name, obj):  # type: ignore
    if collector.funcnamefilter(name) and asyncio.iscoroutinefunction(obj):
        return list(collector._genfunctions(name, obj))


@pytest.mark.tryfirst
def pytest_pyfunc_call(pyfuncitem):  # type: ignore
    if not asyncio.iscoroutinefunction(pyfuncitem.function):
        return

    event_loop = pyfuncitem.funcargs.get("loop", None)
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
            pyfuncitem.obj(**kwargs),
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
def _loop(event_loop_policy):
    try:
        asyncio.set_event_loop_policy(event_loop_policy)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            yield loop
        finally:
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


def get_unused_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[-1]
    sock.close()
    return port


@pytest.fixture
def aiomisc_unused_port_factory() -> t.Callable[[], int]:
    return get_unused_port


@pytest.fixture
def aiomisc_unused_port() -> int:
    return get_unused_port()
