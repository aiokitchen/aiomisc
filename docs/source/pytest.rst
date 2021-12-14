Pytest plugin
=============

This package contains a plugin for pytest.

Basic usage
+++++++++++

Simple usage example:

.. code-block:: python

    import asyncio
    import pytest


    async def test_sample(loop):
        f = loop.crete_future()
        loop.call_soon(f.set_result, True)

        assert await f


asynchronous fixture example:


.. code-block:: python

    import asyncio
    import pytest


    @pytest.fixture
    async def my_fixture(loop):
        await asyncio.sleep(0)

        # Requires python 3.6+
        yield

In case you have to save an instance of an async fixture between tests,
the wrong solution is just changing the fixture scope.
But why it wouldn't work? That's because, in the base scenario, the ``loop``
fixture creates a new event loop instance per test which will be closed after
test teardown. When you have to use an async fixture any caller of
``asyncio.get_event_loop()`` will get the current event loop instance which
will be closed and the next test will run in another event loop.
So the solution is to redefine the ``loop`` fixture with the required scope
and custom fixture with the required scope.

.. code-block:: python

    import asyncio
    import pytest
    from aiomisc import entrypoint


    @pytest.fixture(scope='module')
    def loop():
        with entrypoint() as loop:
            asyncio.set_event_loop(loop)
            yield loop


    @pytest.fixture(scope='module')
    async def sample_fixture(loop):
        yield 1


    LOOP_ID = None


    async def test_using_fixture(sample_fixture):
        global LOOP_ID
        LOOP_ID = id(asyncio.get_event_loop())
        assert sample_fixture == 1


    async def test_not_using_fixture(loop):
        assert id(loop) == LOOP_ID


pytest markers
++++++++++++++

Package contains some useful markers for pytest:

* ``catch_loop_exceptions`` - uncaught event loop exceptions will failling test.
* ``forbid_get_event_loop`` - forbids call ``asyncio.get_event_loop``
  during test case.

.. code-block:: python

    import pytest


    # Test will be failed
    @pytest.mark.forbid_get_event_loop
    async def test_with_get_loop():
        def switch_context():
            loop = get_event_loop()
            future = loop.create_future()
            loop.call_soon(future.set_result, True)
            return future

        with pytest.raises(Failed):
            await switch_context()


    # Test will be failed
    @pytest.mark.catch_loop_exceptions
    async def test_with_errors(loop):
        async def fail():
            # switch context
            await asyncio.sleep(0)
            raise Exception()

        loop.create_task(fail())
        await asyncio.sleep(0.1)
        return


Passing default context
+++++++++++++++++++++++

.. code-block:: python

    import pytest


    @pytest.fixture
    def default_context():
        return {
            'foo': 'bar',
            'bar': 'foo',
        }


Testing services
++++++++++++++++

Redefine ``services`` fixture in your test module:

.. code-block:: python

    @pytest.fixture
    def services(aiomisc_unused_port, handlers):
        return [
            RPCServer(
                handlers={'foo': lambda: 'bar'},
                address='localhost',
                port=aiomisc_unused_port
            )
        ]


Event loop policy overriding
++++++++++++++++++++++++++++

.. code-block:: python

    import uvloop
    import tokio

    policy_ids = ('uvloop', 'asyncio', 'tokio')
    policies = (uvloop.EventLoopPolicy(),
                asyncio.DefaultEventLoopPolicy(),
                tokio.EventLoopPolicy())

    @pytest.fixture(params=policies, ids=policy_ids)
    def event_loop_policy(request):
        return request.param


Thread pool overriding
++++++++++++++++++++++

.. code-block:: python

    thread_pool_ids = ('aiomisc pool', 'default pool')
    thread_pool_implementation = (ThreadPoolExecutor,
                                  concurrent.futures.ThreadPoolExecutor)


    @pytest.fixture(params=thread_pool_implementation, ids=thread_pool_ids)
    def thread_pool_executor(request):
        return request.param


entrypoint arguments
++++++++++++++++++++

.. code-block:: python

    import pytest

    @pytest.fixture
    def entrypoint_kwargs() -> dict:
        return dict(log_config=False)


aiohttp test client
+++++++++++++++++++

.. code-block:: python

    import pytest
    from myapp.services.rest import REST


    @pytest.fixture
    def rest_port(aiomisc_unused_port_factory):
        return aiomisc_unused_port_factory()


    @pytest.fixture
    def rest_service(rest_port):
        return REST(port=rest_port)


    @pytest.fixture
    def services(rest_service):
        return [rest_service]


    @pytest.fixture
    def api_client(api_service):
        test_srv = TestServer(
            app=rest_service.app,
            port=arguments.port,
        )

        return TestClient(test_srv)

    ...


TCPProxy
++++++++

Simple TCP proxy for emulate network problems. Available as fixture `tcp_proxy`


Examples:

.. code-block:: python

    import asyncio
    import time

    import pytest

    import aiomisc


    class EchoServer(aiomisc.service.TCPServer):
        async def handle_client(
                self, reader: asyncio.StreamReader,
                writer: asyncio.StreamWriter
        ):
            chunk = await reader.read(65534)
            while chunk:
                writer.write(chunk)
                chunk = await reader.read(65534)

            writer.close()
            await writer.wait_closed()


    @pytest.fixture()
    def server_port(aiomisc_unused_port_factory) -> int:
        return aiomisc_unused_port_factory()


    @pytest.fixture()
    def services(server_port, localhost):
        return [EchoServer(port=server_port, address=localhost)]


    @pytest.fixture()
    async def proxy(tcp_proxy, localhost, server_port):
        async with tcp_proxy(localhost, server_port) as proxy:
            yield proxy


    async def test_proxy_client_close(proxy):
        reader, writer = await proxy.create_client()
        payload = b"Hello world"

        writer.write(payload)
        response = await asyncio.wait_for(reader.read(1024), timeout=1)

        assert response == payload

        assert not reader.at_eof()
        await proxy.disconnect_all()

        assert await asyncio.wait_for(reader.read(), timeout=1) == b""
        assert reader.at_eof()


    async def test_proxy_client_slow(proxy):
        read_delay = 0.1
        write_delay = 0.2

        # Emulation of asymmetric and slow ISP
        with proxy.slowdown(read_delay, write_delay):
            reader, writer = await proxy.create_client()
            payload = b"Hello world"

            delta = -time.monotonic()

            writer.write(payload)
            await asyncio.wait_for(reader.read(1024), timeout=2)

            delta += time.monotonic()

            assert delta >= read_delay + write_delay


    async def test_proxy_client_with_processor(proxy):
        processed_request = b"Never say hello"

        # Patching protocol functions
        proxy.set_content_processors(
            # Process data from client to server
            lambda _: processed_request,

            # Process data from server to client
            lambda chunk: chunk[::-1],
        )

        reader, writer = await proxy.create_client()
        writer.write(b'nevermind')

        response = await reader.read(16)

        assert response == processed_request[::-1]
