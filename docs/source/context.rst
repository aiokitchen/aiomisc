Context
=======

Services can require each other's data. In this case, you should use ``Context``.

``Context`` is a repository associated with the running ``entrypoint``.

``Context``-object will be created when ``entrypoint`` starts and linked
to the running event loop.

Cross-dependent services might await or set each other's data via the context.

For service instances ``self.context`` is available since ``entrypoint``
started. In other cases ``get_context()`` function returns current context.


.. code-block:: python
    :name: test_context

    import asyncio
    from random import random, randint

    from aiomisc import entrypoint, get_context, Service


    class LoggingService(Service):
        async def start(self):
            context = get_context()

            wait_time = await context['wait_time']

            print('Wait time is', wait_time)
            self.start_event.set()

            while True:
                print('Hello from service', self.name)
                await asyncio.sleep(wait_time)


    class RemoteConfiguration(Service):
        async def start(self):
            # querying from remote server
            await asyncio.sleep(random())

            self.context['wait_time'] = randint(1, 5)


    services = (
        LoggingService(name='#1'),
        LoggingService(name='#2'),
        LoggingService(name='#3'),
        RemoteConfiguration()
    )

    with entrypoint(*services) as loop:
        pass


.. note::

    It's not a silver bullet. In base case services can be configured by
    passing kwargs to the service ``__init__`` method.
