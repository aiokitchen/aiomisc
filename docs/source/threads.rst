Working with threads
====================

Why use threads with asyncio?
-----------------------------

Asyncio is designed for non-blocking I/O operations, but many libraries and
operations are inherently blocking:

* File I/O (reading/writing files)
* CPU-intensive computations
* Legacy libraries without async support
* Database drivers without async support
* System calls that don't have async alternatives

Running blocking code directly in an async function blocks the entire event
loop, preventing other coroutines from executing. The solution is to run
blocking code in separate threads while the event loop continues processing
other tasks.

aiomisc provides convenient decorators and utilities to seamlessly integrate
blocking code with asyncio, powered by the `aiothreads`_ library.

.. _aiothreads: https://pypi.org/project/aiothreads/

Quick reference
---------------

+--------------------------------+------------------------------------------------+
| Decorator/Class                | Use case                                       |
+================================+================================================+
| ``@threaded``                  | Run blocking function in thread pool           |
+--------------------------------+------------------------------------------------+
| ``@threaded_separate``         | Run blocking function in new thread            |
+--------------------------------+------------------------------------------------+
| ``@threaded_iterable``         | Async iterate over blocking generator          |
+--------------------------------+------------------------------------------------+
| ``@threaded_iterable_separate``| Same, but on separate thread                   |
+--------------------------------+------------------------------------------------+
| ``IteratorWrapper``            | Wrap existing generator for async iteration    |
+--------------------------------+------------------------------------------------+
| ``sync_await``                 | Call async function from thread                |
+--------------------------------+------------------------------------------------+
| ``FromThreadChannel``          | Send data from thread to async code            |
+--------------------------------+------------------------------------------------+


``@aiomisc.threaded``
---------------------

Wraps a blocking function to run it in the current thread pool. The decorated
function becomes awaitable.

Basic usage
+++++++++++

.. code-block:: python

    import asyncio
    import time
    from aiomisc import threaded


    @threaded
    def blocking_function():
        time.sleep(1)
        return "done"


    async def main():
        # Run two blocking calls in parallel
        results = await asyncio.gather(
            blocking_function(),
            blocking_function(),
        )
        print(results)  # ['done', 'done']


    asyncio.run(main())


Calling modes
+++++++++++++

The ``@threaded`` decorator returns a ``Threaded`` object with multiple
calling methods:

.. code-block:: python

    import time
    from aiomisc import threaded


    @threaded
    def blocking_function():
        time.sleep(0.1)
        return "result"


    async def main():
        # Async call (returns coroutine)
        result = await blocking_function()

        # Explicit async call
        result = await blocking_function.async_call()

        # Synchronous call (blocks current thread)
        result = blocking_function.sync_call()


Works with methods
++++++++++++++++++

The decorator works correctly with instance methods, class methods,
and static methods:

.. code-block:: python

    from aiomisc import threaded


    class MyClass:
        def __init__(self, value):
            self.value = value

        @threaded
        def instance_method(self):
            return self.value

        @threaded
        @classmethod
        def class_method(cls):
            return cls.__name__

        @threaded
        @staticmethod
        def static_method(x):
            return x * 2


    async def main():
        obj = MyClass(42)
        print(await obj.instance_method())       # 42
        print(await MyClass.class_method())      # MyClass
        print(await MyClass.static_method(21))   # 42


``@aiomisc.threaded_separate``
------------------------------

Wraps a blocking function to run it in a new separate thread (not from pool).
Use this for long-running background tasks that would otherwise occupy a
thread pool slot for extended periods.

.. code-block:: python

    import asyncio
    import time
    import threading
    import aiomisc


    @aiomisc.threaded
    def quick_task():
        """Short task - uses thread pool"""
        time.sleep(0.1)
        return "quick"


    @aiomisc.threaded_separate
    def long_running_task(stop_event: threading.Event):
        """Long task - runs in dedicated thread"""
        while not stop_event.is_set():
            print("Working...")
            time.sleep(1)
        return "finished"


    async def main():
        stop_event = threading.Event()

        # Schedule stop after 5 seconds
        loop = asyncio.get_event_loop()
        loop.call_later(5, stop_event.set)

        # Both run concurrently
        results = await asyncio.gather(
            quick_task(),
            long_running_task(stop_event),
        )
        print(results)  # ['quick', 'finished']


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


Threaded iterators
------------------

``@aiomisc.threaded_iterable``
++++++++++++++++++++++++++++++

Wraps a blocking generator function to make it async-iterable. The generator
runs in a thread pool while yielding values to async code.

.. note::

    The generator uses lazy start - execution begins only when iteration
    starts (first ``async for`` or ``__anext__()`` call), not when entering
    the async context manager.

.. code-block:: python

    import asyncio
    import aiomisc


    @aiomisc.threaded_iterable
    def read_large_file(path):
        """Read file line by line without blocking event loop"""
        with open(path, 'r') as f:
            for line in f:
                yield line.strip()


    async def main():
        async with read_large_file('/etc/hosts') as lines:
            async for line in lines:
                print(line)


    asyncio.run(main())


Buffer size control
^^^^^^^^^^^^^^^^^^^

Use ``max_size`` parameter to control backpressure. The generator thread
will block when the buffer is full:

.. code-block:: python

    import aiomisc


    # Buffer holds at most 2 items
    @aiomisc.threaded_iterable(max_size=2)
    def produce_data():
        for i in range(1000):
            yield i  # Blocks when 2 items buffered


``@aiomisc.threaded_iterable_separate``
+++++++++++++++++++++++++++++++++++++++

Same as ``@threaded_iterable`` but runs in a dedicated thread instead of
the thread pool. Use for long-running generators:

.. code-block:: python

    import aiomisc


    @aiomisc.threaded_iterable_separate
    def tail_file(path):
        """Continuously read new lines from file"""
        with open(path, 'r') as f:
            f.seek(0, 2)  # Go to end
            while True:
                line = f.readline()
                if line:
                    yield line.strip()


Cleanup with context managers
+++++++++++++++++++++++++++++

For infinite generators, always use async context manager or call ``.close()``:

.. code-block:: python

    import aiomisc


    @aiomisc.threaded_iterable(max_size=2)
    def infinite_generator():
        counter = 0
        while True:
            yield counter
            counter += 1


    async def main():
        # Option 1: Context manager (recommended)
        async with infinite_generator() as gen:
            async for value in gen:
                if value >= 10:
                    break  # Context manager handles cleanup

        # Option 2: Manual cleanup
        gen = infinite_generator()
        async for value in gen:
            if value >= 10:
                break
        await gen.close()  # Must call close!


``aiomisc.IteratorWrapper``
---------------------------

Wraps an existing generator to make it async-iterable. Useful when you can't
use decorators or need to specify a custom executor:

.. code-block:: python

    import concurrent.futures
    import aiomisc


    def my_generator():
        for i in range(100):
            yield i


    async def main():
        # Use default thread pool
        wrapper = aiomisc.IteratorWrapper(
            my_generator,
            max_size=10
        )

        async with wrapper as gen:
            async for item in gen:
                print(item)

        # Or use custom thread pool
        pool = concurrent.futures.ThreadPoolExecutor(2)
        wrapper = aiomisc.IteratorWrapper(
            my_generator,
            executor=pool,
            max_size=10
        )

        async with wrapper as gen:
            async for item in gen:
                print(item)

        pool.shutdown()


``aiomisc.IteratorWrapperSeparate``
-----------------------------------

Same as ``IteratorWrapper`` but runs the generator in a dedicated thread:

.. code-block:: python

    import aiomisc


    def blocking_generator():
        while True:
            yield "data"


    async def main():
        wrapper = aiomisc.IteratorWrapperSeparate(
            blocking_generator,
            max_size=5
        )

        async with wrapper as gen:
            count = 0
            async for item in gen:
                count += 1
                if count >= 100:
                    break


Calling async from threads
--------------------------

``aiomisc.sync_await``
++++++++++++++++++++++

Execute an async function synchronously from a thread. Automatically detects
the running event loop:

.. code-block:: python

    import asyncio
    import aiomisc


    async def async_operation():
        await asyncio.sleep(0.1)
        return "async result"


    @aiomisc.threaded
    def thread_function():
        # Call async function from thread
        result = aiomisc.sync_await(async_operation())
        return f"got: {result}"


    async def main():
        result = await thread_function()
        print(result)  # got: async result


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


``aiomisc.sync_wait_coroutine``
+++++++++++++++++++++++++++++++

Lower-level function that requires explicit loop argument:

.. code-block:: python

    import asyncio
    import aiomisc


    async def fetch_data():
        await asyncio.sleep(0.1)
        return {"key": "value"}


    @aiomisc.threaded
    def process_in_thread(loop):
        # Explicit loop argument
        data = aiomisc.sync_wait_coroutine(loop, fetch_data())
        return data["key"]


    with aiomisc.entrypoint() as loop:
        result = loop.run_until_complete(process_in_thread(loop))
        print(result)  # value


``aiomisc.FromThreadChannel``
-----------------------------

A channel for sending data from threads to async code. Unlike
``IteratorWrapper``, you control when and what to send:

.. code-block:: python

    import asyncio
    import aiomisc


    async def consumer(channel: aiomisc.FromThreadChannel):
        async for item in channel:
            print(f"Received: {item}")


    @aiomisc.threaded_separate
    def producer(channel: aiomisc.FromThreadChannel):
        for i in range(5):
            channel.put(i)  # Send to async consumer
        channel.close()  # Signal end of data


    async def main():
        channel = aiomisc.FromThreadChannel(max_size=2)

        await asyncio.gather(
            consumer(channel),
            producer(channel),
        )


    asyncio.run(main())


``contextvars`` support
-----------------------

All decorators automatically copy context variables to the thread:

.. code-block:: python

    import asyncio
    import contextvars
    import aiomisc


    request_id = contextvars.ContextVar("request_id")


    @aiomisc.threaded
    def log_with_context(message):
        print(f"[{request_id.get()}] {message}")


    async def handle_request(req_id):
        request_id.set(req_id)
        await log_with_context("Processing request")


    async def main():
        await asyncio.gather(
            handle_request("req-001"),
            handle_request("req-002"),
            handle_request("req-003"),
        )


    asyncio.run(main())


Output::

    [req-001] Processing request
    [req-002] Processing request
    [req-003] Processing request


.. note::

    Context variables are copied to threads, so modifications in threads
    don't affect the parent context.


``aiomisc.ThreadPoolExecutor``
------------------------------

A fast thread pool implementation used by aiomisc internally.

Manual setup:

.. code-block:: python

    import asyncio
    from aiomisc import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    thread_pool = ThreadPoolExecutor(4)
    loop.set_default_executor(thread_pool)


.. note::

    The ``entrypoint`` context manager sets this automatically.
    Use the ``pool_size`` argument to control thread pool size:

    .. code-block:: python

        with aiomisc.entrypoint(pool_size=8) as loop:
            ...
