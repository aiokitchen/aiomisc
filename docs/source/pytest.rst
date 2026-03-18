Pytest plugin
=============

.. _aiomisc-pytest: https://pypi.org/project/aiomisc-pytest

All pytest plugin code lives in the ``aiomisc`` package itself.
The aiomisc-pytest_ package is required only for plugin registration
(it contains the pytest entry point). Install both:

.. code-block:: bash

    pip install aiomisc aiomisc-pytest

Basic usage
-----------

The plugin automatically provides an event loop and an entrypoint for every
async test. Simply write ``async def test_...`` functions:

.. code-block:: python

    import asyncio

    async def test_sample(event_loop: asyncio.AbstractEventLoop):
        f = event_loop.create_future()
        event_loop.call_soon(f.set_result, True)
        assert await f

Async fixtures work the same way:

.. code-block:: python

    import asyncio
    import pytest


    @pytest.fixture
    async def my_fixture():
        await asyncio.sleep(0)
        yield "value"


    async def test_with_fixture(my_fixture):
        assert my_fixture == "value"

Fixtures
--------

The plugin provides the following fixtures:

Core fixtures
+++++++++++++

``entrypoint``
    **Scope:** function, autouse

    Creates an ``aiomisc.Entrypoint`` instance using the current
    ``event_loop``. Starts all services from the ``services`` fixture and
    populates the context from ``default_context``.

``localhost``
    **Scope:** session

    Returns the localhost address (``"127.0.0.1"`` or ``"[::1]"`` depending
    on what is available on the system).

``loop_debug``
    **Scope:** session

    Returns the value of ``--aiomisc-debug`` command-line option.

``aiomisc_test_timeout``
    **Scope:** session

    Returns the value of ``--aiomisc-test-timeout`` command-line option.

``thread_pool_size``
    **Scope:** session

    Returns the value of ``--aiomisc-pool-size`` command-line option.

``tcp_proxy``
    **Scope:** session

    Returns the ``TCPProxy`` class for emulating network problems.
    See `TCPProxy`_ section below.

Overridable fixtures
++++++++++++++++++++

These fixtures have sensible defaults but can be overridden in your
``conftest.py`` or test module to change behavior or scope.

``event_loop``
    **Scope:** function, autouse, **Default:** creates a new event loop per test

    Creates and manages an asyncio event loop. Configures thread pool,
    debug mode, and exception handling. Closes the loop on teardown.

    Override this fixture to change its scope (module or session) when you
    need async fixtures that outlive a single test. See
    `Scoped event loops and fixtures`_ for details.

``services``
    **Scope:** function, **Default:** empty list

    Return a list of ``aiomisc.Service`` instances to start inside
    the entrypoint.

    .. code-block:: python

        import aiomisc
        import pytest


        class MyService(aiomisc.Service):
            async def start(self) -> None:
                self.start_event.set()
                await asyncio.sleep(3600)


        @pytest.fixture
        def services():
            return [MyService()]

``default_context``
    **Scope:** function, **Default:** empty dict

    Return a mapping of values to populate in the entrypoint context.

    .. code-block:: python

        import pytest


        @pytest.fixture
        def default_context():
            return {
                "foo": "bar",
                "bar": "foo",
            }

``entrypoint_kwargs``
    **Scope:** function, **Default:** ``{"log_config": False}``

    Return extra keyword arguments for the ``entrypoint()`` constructor.

    .. code-block:: python

        import pytest


        @pytest.fixture
        def entrypoint_kwargs() -> dict:
            return dict(log_config=False)

``thread_pool_executor``
    **Scope:** function, **Default:** ``aiomisc.ThreadPoolExecutor``

    Return the thread pool executor class to use.

    .. code-block:: python

        import concurrent.futures
        import pytest


        @pytest.fixture
        def thread_pool_executor():
            return concurrent.futures.ThreadPoolExecutor

Port and socket fixtures
++++++++++++++++++++++++

``aiomisc_unused_port_factory``
    **Scope:** function

    A callable factory that returns an unused port on each call.
    Sockets are cleaned up after test teardown.

``aiomisc_unused_port``
    **Scope:** function

    A single unused port number (uses ``aiomisc_unused_port_factory``
    internally).

``aiomisc_socket_factory``
    **Scope:** function

    A callable factory that returns a ``PortSocket(port, socket)``
    named tuple with a bound socket.

Markers
-------

``@pytest.mark.catch_loop_exceptions``
    Uncaught event loop exceptions will fail the test.

    .. code-block:: python

        import asyncio
        import pytest


        @pytest.mark.catch_loop_exceptions
        async def test_with_errors(event_loop):
            async def fail():
                await asyncio.sleep(0)
                raise Exception()

            event_loop.create_task(fail())
            await asyncio.sleep(0.1)

``@pytest.mark.forbid_get_event_loop``
    Forbids calling ``asyncio.get_event_loop()`` during the test.

    .. code-block:: python

        import asyncio
        import pytest


        @pytest.mark.forbid_get_event_loop
        async def test_no_get_loop():
            def bad():
                asyncio.get_event_loop()

            with pytest.raises(Exception):
                bad()

Command-line options
--------------------

``--aiomisc-debug``
    Enable event loop debug mode. Default: ``False``.

``--aiomisc-pool-size``
    Thread pool size. Default: ``4``.

``--aiomisc-test-timeout``
    Per-test timeout in seconds. Default: ``None`` (no timeout).

Environment variables
---------------------

``AIOMISC_USE_UVLOOP``
    Set to ``"0"``, ``"no"``, or ``"false"`` to disable uvloop.
    Default: ``"1"`` (enabled if uvloop is installed).

``AIOMISC_LOOP_AUTOUSE``
    Set to ``"0"`` to disable autouse on ``event_loop`` and ``entrypoint``
    fixtures. Default: ``"1"``.

Scoped event loops and fixtures
--------------------------------

Why change the scope?
+++++++++++++++++++++

By default, ``event_loop`` and ``entrypoint`` are **function-scoped**: a
fresh event loop is created for every test and closed on teardown. This is
the safest default because each test gets a clean state.

However, some async resources are expensive to create and should be shared
across tests: database connection pools, HTTP client sessions, preloaded
caches, and so on. In pytest, you express this by giving the fixture a
wider scope (``"module"`` or ``"session"``).

The problem is that a wider-scoped async fixture **must run on an event loop
that lives at least as long as the fixture itself**. If the fixture is
session-scoped but the event loop is function-scoped, the loop will be
closed after the first test, and the fixture's teardown (and every
subsequent test that uses it) will fail.

The solution: override ``event_loop`` with the same scope as your
widest async fixture.

The key rule
++++++++++++

.. important::

    The ``event_loop`` fixture scope must be **greater than or equal to** the
    scope of every async fixture that depends on it.

    ``session >= module >= class >= function``

    For example, if you have a ``scope="module"`` async fixture, you need at
    least a ``scope="module"`` event loop.

Module-scoped loop
++++++++++++++++++

Override ``event_loop`` in your test module or in a ``conftest.py`` that
applies to the relevant directory:

.. code-block:: python

    import asyncio
    import pytest


    @pytest.fixture(scope="module")
    def event_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            yield loop
        finally:
            loop.close()
            asyncio.set_event_loop(None)


    @pytest.fixture(scope="module")
    async def shared_resource():
        resource = await create_expensive_resource()
        yield resource
        await resource.close()


    async def test_first(shared_resource):
        assert shared_resource is not None


    async def test_second(shared_resource):
        assert shared_resource is not None

All tests in the module share the same event loop and the same
``shared_resource`` instance. The resource is created once before the
first test in the module and torn down after the last one.

Session-scoped loop
+++++++++++++++++++

For fixtures that must survive the entire test session, place a
session-scoped ``event_loop`` override in a ``conftest.py``. Because this
affects every test that inherits it, it is recommended to put it in a
subdirectory ``conftest.py`` rather than the root one, so that only the
tests that need it are affected.

.. code-block:: bash

    tests/
        conftest.py               # root conftest (default fixtures)
        test_unit.py              # uses default function-scoped loop
        integration/
            conftest.py           # session-scoped event_loop override
            test_database.py      # shares the session loop
            test_api.py           # shares the session loop

.. code-block:: python

    # tests/integration/conftest.py
    import asyncio
    import pytest


    @pytest.fixture(scope="session")
    def event_loop():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            yield loop
        finally:
            loop.close()
            asyncio.set_event_loop(None)

Then use session-scoped async fixtures as usual:

.. code-block:: python

    # tests/integration/conftest.py (continued)
    import pytest


    @pytest.fixture(scope="session")
    async def db_pool():
        pool = await create_pool(dsn="postgresql://localhost/test")
        yield pool
        await pool.close()

.. code-block:: python

    # tests/integration/test_database.py
    async def test_insert(db_pool):
        async with db_pool.acquire() as conn:
            await conn.execute("INSERT INTO t VALUES (1)")


    async def test_select(db_pool):
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 AS n")
            assert row["n"] == 1

Session-scoped async generator fixtures
++++++++++++++++++++++++++++++++++++++++

Async generator fixtures (those that use ``yield``) require extra care.
When the scope is wider than the ``entrypoint`` fixture, the entrypoint
must not destroy the generator during its own teardown.

This works correctly: the ``entrypoint`` is function-scoped and does not
own the session-scoped event loop, so it will not call
``shutdown_asyncgens`` and the generator survives between tests.

.. code-block:: python

    import pytest


    async def some_agen():
        for i in range(100):
            yield i + 1


    @pytest.fixture(scope="session")
    async def async_gen_fixture():
        agen = some_agen()
        val = await agen.__anext__()
        assert val == 1
        val = await agen.__anext__()
        assert val == 2
        yield val
        # teardown: runs when the session-scoped loop is closing
        new_val = await agen.__anext__()
        assert new_val == 3
        await agen.aclose()


    async def test_first(async_gen_fixture):
        assert async_gen_fixture == 2


    async def test_second(async_gen_fixture):
        assert async_gen_fixture == 2

How it works under the hood
+++++++++++++++++++++++++++

Understanding the interaction between ``event_loop`` and ``entrypoint``
helps explain why this is safe:

1. When ``event_loop`` is overridden with a wider scope, the loop is
   **not** created by the ``entrypoint`` — it is passed in via the
   ``loop=`` parameter.

2. The ``Entrypoint`` tracks whether it created the loop with an internal
   ``_loop_owner`` flag. When the loop is passed from outside,
   ``_loop_owner`` is ``False``.

3. On teardown, ``Entrypoint.graceful_shutdown()`` only calls
   ``loop.shutdown_asyncgens()`` when ``_loop_owner`` is ``True``.
   This means the function-scoped entrypoint teardown will **not**
   destroy async generators that belong to the wider-scoped loop.

4. ``loop.shutdown_asyncgens()`` is eventually called by the
   ``event_loop`` fixture itself during its own teardown — at the
   correct time, after all fixtures with that scope have been finalized.

Mixing scopes
+++++++++++++

You can have a session-scoped loop with both session-scoped and
function-scoped fixtures. Function-scoped async fixtures will run on
the session loop and be created/destroyed per test as usual:

.. code-block:: python

    @pytest.fixture(scope="session")
    async def db_pool():
        """Created once, shared across all tests."""
        pool = await create_pool()
        yield pool
        await pool.close()


    @pytest.fixture
    async def db_connection(db_pool):
        """Created fresh for each test, returned to pool after."""
        async with db_pool.acquire() as conn:
            yield conn


    async def test_query(db_connection):
        await db_connection.execute("SELECT 1")

TCPProxy
--------

``TCPProxy`` is a helper for simulating network problems in tests.
It sits between the client and the server, allowing you to add latency,
disconnect clients, or modify traffic on the fly.

.. code-block:: python

    import asyncio
    import pytest
    import aiomisc


    class EchoServer(aiomisc.service.TCPServer):
        async def handle_client(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
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


    async def test_echo(proxy):
        reader, writer = await proxy.create_client()
        writer.write(b"Hello world")
        response = await asyncio.wait_for(reader.read(1024), timeout=1)
        assert response == b"Hello world"


    async def test_disconnect(proxy):
        reader, writer = await proxy.create_client()
        writer.write(b"Hello world")
        await asyncio.wait_for(reader.read(1024), timeout=1)

        await proxy.disconnect_all()
        assert await asyncio.wait_for(reader.read(), timeout=1) == b""


    async def test_slowdown(proxy):
        with proxy.slowdown(read_delay=0.1, write_delay=0.2):
            reader, writer = await proxy.create_client()
            writer.write(b"Hello world")
            response = await asyncio.wait_for(
                reader.read(1024), timeout=2,
            )
            assert response == b"Hello world"


    async def test_content_processor(proxy):
        proxy.set_content_processors(
            lambda _: b"replaced",       # client -> server
            lambda chunk: chunk[::-1],   # server -> client
        )

        reader, writer = await proxy.create_client()
        writer.write(b"original")

        response = await reader.read(16)
        assert response == b"replaced"[::-1]
