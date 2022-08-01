Tutorial
========


``aiomisc`` - this is a collection of utilities into one library that help
you write asynchronous services.


The main approach in this library is to split your program into independent
services that can work competitively in asynchronous mode. The library also
provides a set of ready-to-use services with pre-written start and stop logic.

The vast majority of functions and classes are written in such a way that
they can be used in a program that was not originally designed according
to the principles outlined in this manual. This means that if you don't
plan to modify your code too much, but only use a few useful functions or
classes for you, then everything should work.


Services
++++++++

If you want to run a tcp or web server, then you will
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
``asyncio.run(example_async_func())`` which available since Python 3.7,
the function takes an instance of a coroutine and terminates
all incomplete tasks after it completes. To continue executing the code
indefinitely, you can perform the following trick:

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


If the user presses `Ctrl+C`, the program simply terminates, but if you
want to explicitly free up some resources, for example, close database
connections or rolling back all incomplete transactions, then you have to
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


This solution wins because it is implemented without any external libraries.
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
logic again, but already in the ``except`` block.

In order to describe the logic of starting and stopping in one place, as well
as testing in one single way, and the abstraction ``Service`` is exists.

The service is an abstract base class in which you need to implement the
``start()`` method and not necessarily the ``stop()`` method.

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

So the services are declared, what's next? ``asyncio.run`` does not know how
to work with them, it has not become easier to call them manually,
what can I offer here?

Probably the most magical and complex code in the library is ``entrypoint``.
By the way, it has been tested quite well. Initially, the idea of
``entrypoint`` was to do a lot of routine for me, setting up logs,
setting up a thread pool, well, starting and stopping services correctly.

Let me show you an example:

.. code-block:: python

    import asyncio
    import aiomisc


    ...

    with aiomisc.entrypoint(
        OrdinaryService(),
        InfinityService()
    ) as loop:
        loop.run_forever()

In this example, we launch the two services described above and continue
execution until the user interrupts it. Further, thanks to the context manager,
we correctly terminate all instances of services.

I mentioned that I wanted to remove a lot of routine, let's look at the same
example, just explicitly pass all the default parameters to the ``entrypoint``
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

Let's not describe on what each parameter does. But in general, ``entrypoint``
created an event-loop, a thread pool with 4 threads, set it for the current
event-loop, configured a logger with colored logs and buffered output,
and launched two services.

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

It is also worth paying attention to the ``aiomisc.run`` shortcut,
which is similar in its purpose to ``asyncio.run`` while supporting the
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

    As I mentioned earlier, the library contains a lots of already realized
    abstract services that you can use in your project by simply realize
    several methods.

    A full list of services and theirs usage examples can be found
    on the :doc:`Services page </services>`.
