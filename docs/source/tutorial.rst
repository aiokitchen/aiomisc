Tutorial
========


``aiomisc`` - is a one library collection of utilities that helps
you write asynchronous services.

The main approach in this library is to split your program into independent
services that can work concurrently in asynchronous mode. The library also
provides a set of ready-to-use services with pre-written start and stop logic.

The vast majority of functions and classes are written in such a way that
they can be used in a program that was not originally designed according
to the principles outlined in this manual. This means that if you don't
plan to modify your code too much, but only use a few useful functions or
classes, then everything should work.


Services
++++++++

If you want to run a tcp or web server, you will
have to write something like this:

.. code-block:: python

    import asyncio

    async def example_async_func():
        # do my async business logic
        await init_db()
        await init_cache()
        await start_http_server()
        await start_metrics_server()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(example_async_func())
    # Continue running all background tasks
    loop.run_forever()

In order to start or stop an async programs, usually using function
``asyncio.run(example_async_func())`` which available since Python 3.7.
This function takes an instance of a coroutine and cancels
all still running tasks before returning a result.
To continue executing the code indefinitely,
you can perform the following trick:

.. code-block:: python

    import asyncio

    async def example_async_func():
        # do my async business logic
        await init_db()
        await init_cache()
        await start_http_server()
        await start_metrics_server()

        # Make future which never be done
        # using instead loop.run_forever()
        await asyncio.Future()

    asyncio.run(example_async_func())


When the user presses `Ctrl+C`, the program simply terminates, but if you
want to explicitly free up some resources, for example, close database
connections or rolling back incomplete transactions, then you have to
do something like this:

.. code-block:: python

    import asyncio

    async def example_async_func():
        try:
            # do my async business logic
            await init_db()
            await init_cache()
            await start_http_server()
            await start_metrics_server()

            # Make future which never be done
            # using instead loop.run_forever()
            await asyncio.Future()
        except asyncio.CancelledError:
            # Do this block when SIGTERM has been received
            pass
        finally:
            # Do this block on exit
            ...

    asyncio.run(example_async_func())


It is a good solution because it is implemented without any 3rd-party libraries.
When your program starts to grow, you will probably want to optimize the
startup time in a simple way, namely to do all initialization competitively.
At first glance it seems that this code will solve the problem:


.. code-block:: python

    import asyncio

    async def example_async_func():
        try:
            # do my async business logic
            await asyncio.gather(
                init_db(),
                init_cache(),
                start_http_server(),
                start_metrics_server(),
            )

            # Make future which never be done
            # using instead loop.run_forever()
            await asyncio.Future()
        except asyncio.CancelledError:
            # Do this block when SIGTERM has been received
            pass
        finally:
            # Do this block on exit
            ...

    asyncio.run(example_async_func())

But if suddenly some part of the initialization does not go according to plan,
then you somehow have to figure out what exactly went wrong, so with concurrent
execution, the code will no longer be as simple as in this example.

And in order to somehow organize the code, you should make
a separate function that will contain the ``try/except/finally`` block and
contain error handling.


.. code-block:: python

    import asyncio

    async def init_db():
        try:
            # initialize connection
        finally:
            # close connection
            ...

    async def example_async_func():
        try:
            # do my async business logic
            await asyncio.gather(
                init_db(),
                init_cache(),
                start_http_server(),
                start_metrics_server(),
            )

            # Make future which never be done
            # using instead loop.run_forever()
            await asyncio.Future()
        except asyncio.CancelledError:
            # Do this block when SIGTERM has been received
            # TODO: shutdown all things correctly
            pass
        finally:
            # Do this block on exit
            ...

    asyncio.run(example_async_func())


And now if the user presses Ctrl+C, you need to describe the shutdown
logic again, but now in the ``except`` block.

In order to describe the logic of starting and stopping in one place, as well
as testing in one single way, there is a ``Service`` abstraction.

The service is an abstract base class with mandatory ``start()`` and
optional ``stop()`` methods.

The service can operate in two modes. The first is when the ``start()`` method
runs forever, then you do not need to implement a ``stop()``, but you need
to report that the initialization is successfully completed by
setting ``self.start_event.set()``.


.. code-block:: python

    import asyncio
    import aiomisc


    class InfinityService(aiomisc.Service):
        async def start(self):
            # Service is ready
            self.start_event.set()

            while True:
                # do some staff
                await asyncio.sleep(1)

In this case, stopping the service will consist in the completion of the
coroutine that was created by ``start()``.

The second method is an explicit description of the way
to ``start()`` and ``stop()``.


.. code-block:: python

    import asyncio
    import aiomisc
    from typing import Any


    class OrdinaryService(aiomisc.Service):
        async def start(self):
            # do some staff
            ...

        async def stop(self, exception: Exception = None) -> Any:
            # do some staff
            ...

In this case, the service will be started and stopped once.


``entrypoint``
++++++++++++++

So the service abstraction is declared, what's next? ``asyncio.run`` does
not know how to work with them, calling them manually has not become easier,
what can this library offer here?

Probably the most magical, complex, and at the same time quite well-tested
code in the library is ``entrypoint``. Initially, the idea of
``entrypoint`` was to get rid of the routine: setting up logs,
setting up a thread pool, as well as starting and stopping services correctly.

Lets check an example:

.. code-block:: python

    import asyncio
    import aiomisc

    ...

    with aiomisc.entrypoint(
        OrdinaryService(),
        InfinityService()
    ) as loop:
        loop.run_forever()

In this example, we will launch the two services described above and continue
execution until the user interrupts them. Next, thanks to the context
manager, we correctly terminate all instances of services.

As mentioned above I just wanted to remove a lot of routine, let's look at the
same example, just pass all the default parameters to the ``entrypoint``
explicitly.

.. code-block:: python

    import asyncio
    import aiomisc


    ...

    with aiomisc.entrypoint(
        OrdinaryService(),
        InfinityService(),
        pool_size=4,
        log_level="info",
        log_format="color",
        log_buffering=True,
        log_buffer_size=1024,
        log_flush_interval=0.2,
        log_config=True,
        policy=asyncio.DefaultEventLoopPolicy(),
        debug=False
    ) as loop:
        loop.run_forever()

Let's not describe what each parameter does. But in general,
``entrypoint`` has create an event-loop, a four threads pool, set
it for the current event-loop, has configure a colored logger with
buffered output, and launched two services.

You can also run the ``entrypoint`` without services,
just configure logging and so on.:

.. code-block:: python

    import asyncio
    import logging
    import aiomisc


    async def sleep_and_exit():
        logging.info("Started")
        await asyncio.sleep(1)
        logging.info("Exiting")


    with aiomisc.entrypoint(log_level="info") as loop:
        loop.run_until_complete(sleep_and_exit())

It is also worth paying attention to the ``aiomisc.run``,
which is similar by its purpose to ``asyncio.run`` while supporting the
start and stop of services and so on.

.. code-block:: python

    import asyncio
    import logging
    import aiomisc


    async def sleep_and_exit():
        logging.info("Started")
        await asyncio.sleep(1)
        logging.info("Exiting")


    aiomisc.run(
        # the first argument
        # is a main coroutine
        sleep_and_exit(),
        # Other positional arguments
        # is service instances
        OrdinaryService(),
        InfinityService(),
        # keyword arguments will
        # be passed as well to the entrypoint
        log_level="info"
    )

.. note::

    As I mentioned above, the library contains lots of already realized
    abstract services that you can use in your project by simply implement
    several methods.

    A full list of services and usage examples can be found on the
    on the :doc:`Services page </services>`.

Executing code in thread or process-pools
+++++++++++++++++++++++++++++++++++++++++

.. _working with threads: https://docs.python.org/3/library/asyncio-eventloop.html#executing-code-in-thread-or-process-pools

As explained in `working with threads`_ section in official python
documentation asyncio event loop starts thread pool.

This pool is needed in order to run, for example, name resolution and not
blocks the event loop while low-level ``gethostbyname`` call works.

The size of this thread pool should be configured at application startup,
otherwise you may run into all sorts of problems when this pool is
too large or too small.

By default, the ``entrypoint`` creates a thread pool with size equal to
the number of CPU cores, but not less than 4 and no more than 32 threads.
Of course you can specify as you need.

``@aiomisc.threaded`` decorator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The following recommendations for calling blocking functions in threads given
in `working with threads`_ section in official Python documentation:

.. code-block:: python

    import asyncio

    def blocking_io():
        # File operations (such as logging) can block the event loop.
        with open('/dev/urandom', 'rb') as f:
            return f.read(100)

    async def main():
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, blocking_io)

    asyncio.run(main())

This library provides a very simple way to do the same:

.. code-block:: python

    import aiomisc

    @aiomisc.threaded
    def blocking_io():
        with open('/dev/urandom', 'rb') as f:
            return f.read(100)

    async def main():
        result = await blocking_io()

    aiomisc.run(main())

As you can see in this example, it is enough to wrap the function
with a decorator ``aiomisc.threaded``, after that it will return an
awaitable object, but the code inside the function will be
sent to the default thread pool.

``@aiomisc.threaded_separate`` decorator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If the blocking function runs for a long time, or even indefinitely,
in other words, if the cost of creating a thread is insignificant compared
to the workload, then you can use the decorator ``aiomisc.threaded_separate``.

.. code-block:: python

    import hashlib
    import aiomisc

    @aiomisc.threaded_separate
    def another_one_useless_coin_miner():
        with open('/dev/urandom', 'rb') as f:
            hasher = hashlib.sha256()
            while True:
                hasher.update(f.read(1024))
                if hasher.hexdigest().startswith("0000"):
                    return hasher.hexdigest()

    async def main():
        print(
            "the hash is",
            await another_one_useless_coin_miner()
        )

    aiomisc.run(main())

.. note::

    This approach allows you not to occupy threads in the pool for a long
    time, but at the same time does not limit the number of created threads
    in any way.

More examples you can be found in :doc:`/threads`.

``@aiomisc.threaded_iterable`` decorator
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

If a generator needs to be executed in a thread, there are problems with
synchronization of the thread and the eventloop. This library provides a
custom decorator designed to turn a synchronous generator into an
asynchronous one.

This is very useful if, for example, a queue or database driver has written
synchronous, but you want to use it efficiently in asynchronous code.

.. code-block:: python

    import aiomisc

    @aiomisc.threaded_iterable(max_size=8)
    def urandom_reader():
        with open('/dev/urandom', "rb") as fp:
            while True:
                yield fp.read(8)

    async def main():
        counter = 0
        async for chunk in urandom_reader():
            print(chunk)
            counter += 1
            if counter > 16:
                break

    aiomisc.run(main())

Under the hood, this decorator returns a special object that has a queue, and
asynchronous iterator interface provides access to that queue.

You should always specify the ``max_size`` parameter, which limits the
size of this queue and prevents threaded code from sending too much items to
asynchronous code, in case the asynchronous iteration in case the asynchronous
iteration slacking.
