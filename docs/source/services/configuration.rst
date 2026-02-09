Service Configuration
=====================

This section covers running multiple services and service configuration options.


Multiple services
+++++++++++++++++

Pass several service instances to the ``entrypoint`` to run all of them.
After exiting the entrypoint service instances will be gracefully shut down.

.. code-block:: python

    import asyncio
    from aiomisc import entrypoint
    from aiomisc.service import Service, TCPServer, UDPServer


    class LoggingService(PeriodicService):
        async def callback(self):
            print('Hello from service', self.name)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())


    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    services = (
        LoggingService(name='#1', interval=1),
        EchoServer(address='localhost', port=8901),
        UDPPrinter(address='localhost', port=3000),
    )


    with entrypoint(*services) as loop:
        loop.run_forever()


Configuration
+++++++++++++

``Service`` metaclass accepts all kwargs and will set it
to ``self`` as attributes.

.. code-block:: python

    import asyncio
    from aiomisc import entrypoint
    from aiomisc.service import Service, TCPServer, UDPServer


    class LoggingService(Service):
        # required kwargs
        __required__ = frozenset({'name'})

        # default value
        delay: int = 1

        async def start(self):
            self.start_event.set()
            while True:
                # attribute ``name`` from kwargs
                # must be defined when instance initializes
                print('Hello from service', self.name)

                # attribute ``delay`` from kwargs
                await asyncio.sleep(self.delay)

    services = (
        LoggingService(name='#1'),
        LoggingService(name='#2', delay=3),
    )


    with entrypoint(*services) as loop:
        loop.run_forever()
