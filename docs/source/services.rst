Services
========

``Services`` is an abstraction to help organize lots of different
tasks in one process. Each service must implement ``start()`` method and can
implement ``stop()`` method.

Service instance should be passed to the ``entrypoint``, and will be started
after the event loop has been created.

.. note::

   Current event-loop will be set before ``start()`` method called.
   The event loop will be set as current for this thread.

   Please avoid using ``asyncio.get_event_loop()`` explicitly inside
   ``start()`` method. Use ``self.loop`` instead:

   .. code-block:: python
      :name: test_service_start_event

      import asyncio
      from threading import Event
      from aiomisc import entrypoint, Service

      event = Event()

      class MyService(Service):
        async def start(self):
            # Send signal to entrypoint for continue running
            self.start_event.set()

            event.set()
            # Start service task
            await asyncio.sleep(3600)


      with entrypoint(MyService()) as loop:
          assert event.is_set()


Method ``start()`` creates as a separate task that can run forever. But in
this case ``self.start_event.set()`` should be called for notifying
``entrypoint``.

During graceful shutdown method ``stop()`` will be called first,
and after that, all running tasks will be canceled (including ``start()``).


This package contains some useful base classes for simple services writing.


.. _tcp-server:

``TCPServer``
+++++++++++++

``TCPServer`` - it's a base class for writing TCP servers.
Just implement ``handle_client(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_tcp_server

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer


    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    async def echo_client(host, port):
        reader, writer = await asyncio.open_connection(host=host, port=port)
        writer.write(b"hello\n")
        assert await reader.readline() == b"hello\n"

        writer.write(b"world\n")
        assert await reader.readline() == b"world\n"

        writer.close()
        await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(echo_client("localhost", 8901))


.. _udp-server:

``UDPServer``
+++++++++++++

``UDPServer`` - it's a base class for writing UDP servers.
Just implement ``handle_datagram(data, addr)`` to use it.

.. code-block:: python

    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    with entrypoint(UDPPrinter(address='localhost', port=3000)) as loop:
        loop.run_forever()


``TLSServer``
+++++++++++++

``TLSServer`` - it's a base class for writing TCP servers with TLS.
Just implement ``handle_client(reader, writer)`` to use it.

.. code-block:: python

    class SecureEchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())

    service = SecureEchoServer(
        address='localhost',
        port=8900,
        ca='ca.pem',
        cert='cert.pem',
        key='key.pem',
        verify=False,
    )

    with entrypoint(service) as loop:
        loop.run_forever()


.. _tcp-client:

``TCPClient``
+++++++++++++

``TCPClient`` - it's a base class for writing TCP clients.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_tcp_client

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, TCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(TCPClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
        EchoClient(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``TLSClient``
+++++++++++++

``TLSClient`` - it's a base class for writing TLS clients.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, TCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(TLSClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='server.pem',
            key='server.key',
        ),
        EchoClient(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='client.pem',
            key='client.key',
        ),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``RobustTCPClient``
+++++++++++++++++++

``RobustTCPClient`` - it's a base class for writing TCP clients with
auto-reconnection when connection lost.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_robust_tcp_client

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, RobustTCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(RobustTCPClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
        EchoClient(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``RobustTLSClient``
+++++++++++++++++++

``RobustTLSClient`` - it's a base class for writing TLS clients with
auto-reconnection when connection lost.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, RobustTCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(RobustTLSClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='server.pem',
            key='server.key',
        ),
        EchoClient(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='client.pem',
            key='client.key',
        ),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


.. _periodic-service:

``PeriodicService``
+++++++++++++++++++

``PeriodicService`` runs ``PeriodicCallback`` as a service and waits for
the running callback to complete on the stop method. You need to use ``PeriodicService``
as a base class and override ``callback`` async coroutine method.

Service class accepts required ``interval`` argument - periodic interval
in seconds and
optional ``delay`` argument - periodic execution delay in seconds (0 by default).

.. code-block:: python

    import aiomisc
    from aiomisc.service.periodic import PeriodicService


    class MyPeriodicService(PeriodicService):
        async def callback(self):
            log.info('Running periodic callback')
            # ...

    service = MyPeriodicService(interval=3600, delay=0)  # once per hour

    with entrypoint(service) as loop:
        loop.run_forever()


.. _dns_server:

DNS Server
++++++++++

The DNS server described here uses the ``aiomisc`` library, which provides
utilities for asynchronous I/O operations, and the ``dnslib`` library for
handling DNS records and packets. This setup is ideal for high-performance,
non-blocking DNS query handling.

Key Features
~~~~~~~~~~~~

1. **Asynchronous I/O**: Utilizes asynchronous operations to handle multiple
   DNS queries concurrently, ensuring high performance and scalability.
2. **UDP and TCP Support**: Supports DNS queries over both UDP and TCP
   protocols, making it versatile for various network configurations.
3. **``EDNS0`` Support**: Implements Extension Mechanisms for DNS (``EDNS0``)
   to handle larger DNS messages and extended functionalities.
4. **Customizable DNS Records**: Allows easy configuration of DNS zones
   and records, enabling you to define and manage your DNS entries
   efficiently.

Prerequisites
~~~~~~~~~~~~~

Install the required libraries using pip:

.. code-block::

    pip install aiomisc[dns]


Setting Up the Server
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from aiomisc import entrypoint
    from aiomisc.service.dns import (
        DNSStore, DNSZone, TCPDNSServer, UDPDNSServer, records,
    )

    zone = DNSZone("test.")
    zone.add_record(records.A.create("test.", "10.10.10.10"))
    zone.add_record(records.AAAA.create("test.", "fd10::10"))

    store = DNSStore()
    store.add_zone(zone)
    services = [
        UDPDNSServer(
            store=store, address="::1", port=5053,
        ),
        TCPDNSServer(
            store=store, address="::1", port=5053,
        ),
    ]

    if __name__ == "__main__":
        with entrypoint(*services, log_level="debug") as loop:
            loop.run_forever()


Testing the Server
~~~~~~~~~~~~~~~~~~

You can test the DNS server using tools like ``dig``. For example,
to query the A and AAAA records for ``test.``,
use the following commands:

.. code-block::

    dig @::1 -p 5053 test. A
    dig @::1 -p 5053 test. AAAA
    dig @::1 -p 5053 +tcp test. A
    dig @::1 -p 5053 +tcp test. AAAA


These commands should return the IP addresses
``10.10.10.10`` and ``fd10::10`` respectively, confirming that the
DNS server is working correctly.


Dynamic Store Management
~~~~~~~~~~~~~~~~~~~~~~~~

One of the powerful features of this DNS server setup is the
ability to dynamically manage the DNS store. This allows you
to add or remove zones and records at runtime, without needing
to restart the server.

Managing DNS zones and records dynamically is essential for a
flexible DNS server setup. This guide focuses on how to
manipulate DNS zones and records using the ``DNSStore`` and ``DNSZone``
classes, providing practical examples for each operation.


Adding a Zone
~~~~~~~~~~~~~

You can add a new zone to the ``DNSStore`` to manage its records.
This operation ensures that the zone is available for DNS queries.

.. code-block:: python

    from aiomisc.service.dns import DNSStore, DNSZone

    # Create a DNSStore instance
    dns_store = DNSStore()

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Verify the zone is added
    assert dns_store.get_zone("example.com.") is zone


Removing a Zone
~~~~~~~~~~~~~~~

Removing a zone from the ``DNSStore`` ensures it is no longer available for DNS queries.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Remove the zone from the store
    dns_store.remove_zone("example.com.")

    # Verify the zone is removed
    assert dns_store.get_zone("example.com.") is None


Adding a Record to a Zone
~~~~~~~~~~~~~~~~~~~~~~~~~

To manage DNS entries, you can add records to a specific zone.
This operation makes the record available for DNS resolution within that zone.

.. code-block:: python

    from aiomisc.service.dns.records import A, RecordType

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record
    record = A.create(name="www.example.com.", ip="192.0.2.1")

    # Add the record to the zone
    zone.add_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the record
    records = dns_store.query("www.example.com.", RecordType.A)

    # Verify the record is added
    assert record in records


Querying Records
~~~~~~~~~~~~~~~~

You can query the ``DNSStore`` to retrieve records for a specific domain
name. This is useful to verify if a record exists or to handle DNS queries.

.. code-block:: python

    # Query the store for a nonexistent record
    records = dns_store.query("nonexistent.example.com.", RecordType.A)

    # Verify no records are found
    assert len(records) == 0


Handling Duplicate Zones
~~~~~~~~~~~~~~~~~~~~~~~~

Attempting to add a zone that already exists should raise an error,
ensuring that each zone is unique within the ``DNSStore``.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Attempt to add the same zone again
    try:
        dns_store.add_zone(zone)
    except ValueError as e:
        print(f"Error: {e}")


Removing a Nonexistent Zone
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Removing a zone that does not exist should raise an error,
indicating that the operation is invalid.

.. code-block:: python

    # Attempt to remove a nonexistent zone
    try:
        dns_store.remove_zone("nonexistent.com.")
    except ValueError as e:
        print(f"Error: {e}")


Querying Subdomains
~~~~~~~~~~~~~~~~~~~

The ``DNSStore`` supports querying subdomains, allowing you to resolve
records within subdomains of an existing zone.

.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record for a subdomain
    record = A.create(name="sub.example.com.", ip="192.0.2.2")

    # Add the record to the zone
    zone.add_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the subdomain record
    records = dns_store.query("sub.example.com.", RecordType.A)

    # Verify the subdomain record is found
    assert record in records


Retrieving a Zone
~~~~~~~~~~~~~~~~~

You can retrieve a zone from the ``DNSStore`` to
inspect or manipulate it further.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Retrieve the zone from the store
    retrieved_zone = dns_store.get_zone("example.com.")

    # Verify the zone is retrieved
    assert retrieved_zone is zone


Handling Nonexistent Zones
~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieving a zone that does not exist should return ``None``.

.. code-block:: python

    # Attempt to retrieve a nonexistent zone
    nonexistent_zone = dns_store.get_zone("nonexistent.com.")

    # Verify no zone is retrieved
    assert nonexistent_zone is None


Removing a Record from a Zone
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To remove a DNS record from a zone, you can use the
``remove_record`` method. This operation ensures the
record is no longer available for DNS resolution.


.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record
    record = A.create(name="www.example.com.", ip="192.0.2.1")

    # Add the record to the zone
    zone.add_record(record)

    # Remove the record from the zone
    zone.remove_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the record
    records = dns_store.query("www.example.com.", RecordType.A)

    # Verify the record is removed
    assert len(records) == 0


Finding Zone by Prefix
~~~~~~~~~~~~~~~~~~~~~~

The ``DNSStore`` can find the appropriate zone for a given domain
name, which is useful for handling queries with subdomains.


.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Find the zone for a subdomain
    zone_prefix = dns_store.get_zone_for_name("sub.example.com.")

    # Verify the correct zone is found
    assert zone_prefix == ("com", "example")

.. _cron-service:

``CronService``
+++++++++++++++

``CronService`` runs ``CronCallback's`` as a service and waits for
running callbacks to complete on the stop method.

It's based on croniter_. You can register async coroutine method with ``spec`` argument - cron like format:

.. _croniter: https://github.com/taichino/croniter

.. warning::

   requires installed croniter_:

   .. code-block::

       pip install croniter

   or using extras:

   .. code-block::

       pip install aiomisc[cron]


.. code-block:: python

    import aiomisc
    from aiomisc.service.cron import CronService


    async def callback():
        log.info('Running cron callback')
        # ...

    service = CronService()
    service.register(callback, spec="0 * * * *") # every hour at zero minutes

    with entrypoint(service) as loop:
        loop.run_forever()


You can also inherit from ``CronService``, but remember that callback registration
should be proceeded before start

.. code-block:: python

    import aiomisc
    from aiomisc.service.cron import CronService


    class MyCronService(CronService):
        async def callback(self):
            log.info('Running cron callback')
            # ...

        async def start(self):
            self.register(self.callback, spec="0 * * * *")
            await super().start()

    service = MyCronService()

    with entrypoint(service) as loop:
        loop.run_forever()


Multiple services
+++++++++++++++++

Pass several service instances to the ``entrypoint`` to run all of them.
After exiting the entrypoint service instances will be gracefully shut down.

.. code-block:: python

    import asyncio
    from aiomisc import entrypoint
    from aiomisc.service import Service, TCPServer, UDPServer


    class LoggingService(PeriodicService):
        async def callabck(self):
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


.. _aiohttp-service:

aiohttp service
+++++++++++++++

.. warning::

   requires installed aiohttp:

   .. code-block::

       pip install aiohttp

   or using extras:

   .. code-block::

       pip install aiomisc[aiohttp]


aiohttp application can be started as a service:

.. code-block:: python

    import aiohttp.web
    import argparse
    from aiomisc import entrypoint
    from aiomisc.service.aiohttp import AIOHTTPService

    parser = argparse.ArgumentParser()
    group = parser.add_argument_group('HTTP options')

    group.add_argument("-l", "--address", default="::",
                       help="Listen HTTP address")
    group.add_argument("-p", "--port", type=int, default=8080,
                       help="Listen HTTP port")


    async def handle(request):
        name = request.match_info.get('name', "Anonymous")
        text = "Hello, " + name
        return aiohttp.web.Response(text=text)


    class REST(AIOHTTPService):
        async def create_application(self):
            app = aiohttp.web.Application()

            app.add_routes([
                aiohttp.web.get('/', handle),
                aiohttp.web.get('/{name}', handle)
            ])

            return app

    arguments = parser.parse_args()
    service = REST(address=arguments.address, port=arguments.port)

    with entrypoint(service) as loop:
        loop.run_forever()


Class ``AIOHTTPSSLService`` is similar to ``AIOHTTPService`` but creates an HTTPS
server. You must pass SSL-required options (see ``TLSServer`` class).


.. _asgi-service:

asgi service
++++++++++++

.. warning::

   requires installed aiohttp-asgi:

   .. code-block::

       pip install aiohttp-asgi

   or using extras:

   .. code-block::

       pip install aiomisc[asgi]


Any ASGI-like application can be started as a service:

.. code-block:: python

   import argparse

   from fastapi import FastAPI

   from aiomisc import entrypoint
   from aiomisc.service.asgi import ASGIHTTPService, ASGIApplicationType

   parser = argparse.ArgumentParser()
   group = parser.add_argument_group('HTTP options')

   group.add_argument("-l", "--address", default="::",
                      help="Listen HTTP address")
   group.add_argument("-p", "--port", type=int, default=8080,
                      help="Listen HTTP port")


   app = FastAPI()


   @app.get("/")
   async def root():
       return {"message": "Hello World"}


   class REST(ASGIHTTPService):
       async def create_asgi_app(self) -> ASGIApplicationType:
           return app


   arguments = parser.parse_args()
   service = REST(address=arguments.address, port=arguments.port)

   with entrypoint(service) as loop:
       loop.run_forever()


Class ``ASGIHTTPSSLService`` is similar to ``ASGIHTTPService`` but creates
HTTPS server. You must pass SSL-required options (see ``TLSServer`` class).

.. uvicorn-service:

uvicorn service
+++++++++++++++

.. warning::

   requires installed uvicorn:

   .. code-block::

       pip install uvicorn

   or using extras:

   .. code-block::

       pip install aiomisc[uvicorn]


Any ASGI-like application can be started via uvicorn as a service:

.. code-block:: python

   import argparse

   from fastapi import FastAPI

   from aiomisc import entrypoint
   from aiomisc.service.uvicorn import UvicornApplication, UvicornService

   parser = argparse.ArgumentParser()
   group = parser.add_argument_group('HTTP options')

   group.add_argument("-l", "--host", default="::",
                      help="Listen HTTP host")
   group.add_argument("-p", "--port", type=int, default=8080,
                      help="Listen HTTP port")


   app = FastAPI()


   @app.get("/")
   async def root():
       return {"message": "Hello World"}


   class REST(UvicornService):
       async def create_application(self) -> UvicornApplication:
           return app


   arguments = parser.parse_args()
   service = REST(host=arguments.host, port=arguments.port)

   with entrypoint(service) as loop:
       loop.run_forever()




.. _grpc-service::

GRPC service
++++++++++++

This is an example of a GRPC service which is defined in a file and loads a
`hello.proto` file without code generation, this example is one of the examples
from `grpcio`, the other examples will work as expected.

Proto definition:

.. code-block::

    syntax = "proto3";

    package helloworld;

    // The greeting service definition.
    service Greeter {
      // Sends a greeting
      rpc SayHello (HelloRequest) returns (HelloReply) {}
    }

    // The request message containing the user's name.
    message HelloRequest {
      string name = 1;
    }

    // The response message containing the greetings
    message HelloReply {
      string message = 1;
    }


Service initialization example:


.. code-block:: python

    import grpc

    import aiomisc
    from aiomisc.service.grpc_server import GRPCService


    protos, services = grpc.protos_and_services("hello.proto")


    class Greeter(services.GreeterServicer):
        async def SayHello(self, request, context):
            return protos.HelloReply(message='Hello, %s!' % request.name)


    def main():
        grpc_service = GRPCService(compression=grpc.Compression.Gzip)
        services.add_GreeterServicer_to_server(
            Greeter(), grpc_service,
        )
        grpc_service.add_insecure_port('[::]:0')
        grpc_service.add_insecure_port('[::1]:0')
        grpc_service.add_insecure_port('127.0.0.1:0')
        grpc_service.add_insecure_port('localhost:0')
        grpc_service.add_secure_port('localhost:0', grpc.local_server_credentials())
        grpc_service.add_secure_port('[::]:0', grpc.local_server_credentials())

        with aiomisc.entrypoint(grpc_service) as loop:
            loop.run_forever()


    if __name__ == '__main__':
        main()


To enable reflection for the service you use reflection flag:

.. code-block:: python

    GRPCService(reflection=True)


.. _memory-tracer:

Memory Tracer
+++++++++++++

Simple and useful service for logging large python
objects allocated in memory.


.. code-block:: python

    import asyncio
    import os
    from aiomisc import entrypoint
    from aiomisc.service import MemoryTracer


    async def main():
        leaking = []

        while True:
            leaking.append(os.urandom(128))
            await asyncio.sleep(0)


    with entrypoint(MemoryTracer(interval=1, top_results=5)) as loop:
        loop.run_until_complete(main())


Output example:

.. code-block::

    [T:[1] Thread Pool] INFO:aiomisc.service.tracer: Top memory usage:
     Objects | Obj.Diff |   Memory | Mem.Diff | Traceback
          12 |       12 |   1.9KiB |   1.9KiB | aiomisc/periodic.py:40
          12 |       12 |   1.8KiB |   1.8KiB | aiomisc/entrypoint.py:93
           6 |        6 |   1.1KiB |   1.1KiB | aiomisc/thread_pool.py:71
           2 |        2 |   976.0B |   976.0B | aiomisc/thread_pool.py:44
           5 |        5 |   712.0B |   712.0B | aiomisc/thread_pool.py:52

    [T:[6] Thread Pool] INFO:aiomisc.service.tracer: Top memory usage:
     Objects | Obj.Diff |   Memory | Mem.Diff | Traceback
       43999 |    43999 |   7.1MiB |   7.1MiB | scratches/scratch_8.py:11
          47 |       47 |   4.7KiB |   4.7KiB | env/bin/../lib/python3.7/abc.py:143
          33 |       33 |   2.8KiB |   2.8KiB | 3.7/lib/python3.7/tracemalloc.py:113
          44 |       44 |   2.4KiB |   2.4KiB | 3.7/lib/python3.7/tracemalloc.py:185
          14 |       14 |   2.4KiB |   2.4KiB | aiomisc/periodic.py:40


.. _profiler:

Profiler
++++++++

Simple service for profiling.
Optional `path` argument can be provided to dump complete profiling data,
which can be later used by, for example, snakeviz.
Also can change ordering with the `order` argument ("cumulative" by default).


.. code-block:: python

    import asyncio
    import os
    from aiomisc import entrypoint
    from aiomisc.service import Profiler


    async def main():
        for i in range(100):
            time.sleep(0.01)


    with entrypoint(Profiler(interval=0.1, top_results=5)) as loop:
        loop.run_until_complete(main())


Output example:

.. code-block::

   108 function calls in 1.117 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      100    1.117    0.011    1.117    0.011 {built-in method time.sleep}
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:89(__init__)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:99(init)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:118(load_stats)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/cProfile.py:50(create_stats)


.. _raven-service:

Raven service
+++++++++++++

Simple service for sending unhandled exceptions to the `sentry`_
service instance.

.. _sentry: https://sentry.io

Simple example:

.. code-block:: python

   import asyncio
   import logging
   import sys

   from aiomisc import entrypoint
   from aiomisc.version import __version__
   from aiomisc.service.raven import RavenSender


   async def main():
       while True:
           await asyncio.sleep(1)

           try:
               1 / 0
           except ZeroDivisionError:
               logging.exception("Exception")


   raven_sender = RavenSender(
       sentry_dsn=(
           "https://583ca3b555054f80873e751e8139e22a@o429974.ingest.sentry.io/"
           "5530251"
       ),
       client_options=dict(
           # Got environment variable SENTRY_NAME by default
           name="example-from-aiomisc",
           # Got environment variable SENTRY_ENVIRONMENT by default
           environment="simple_example",
           # Got environment variable SENTRY_RELEASE by default
           release=__version__,
       )
   )


   with entrypoint(raven_sender) as loop:
       loop.run_until_complete(main())

Full configuration:

.. code-block:: python

   import asyncio
   import logging
   import sys

   from aiomisc import entrypoint
   from aiomisc.version import __version__
   from aiomisc.service.raven import RavenSender


   async def main():
       while True:
           await asyncio.sleep(1)

           try:
               1 / 0
           except ZeroDivisionError:
               logging.exception("Exception")


   raven_sender = RavenSender(
       sentry_dsn=(
           "https://583ca3b555054f80873e751e8139e22a@o429974.ingest.sentry.io/"
           "5530251"
       ),
       client_options=dict(
           # Got environment variable SENTRY_NAME by default
           name="",
           # Got environment variable SENTRY_ENVIRONMENT by default
           environment="full_example",
           # Got environment variable SENTRY_RELEASE by default
           release=__version__,

           # Default options values
           include_paths=set(),
           exclude_paths=set(),
           auto_log_stacks=True,
           capture_locals=True,
           string_max_length=400,
           list_max_length=50,
           site=None,
           include_versions=True,
           processors=(
               'raven.processors.SanitizePasswordsProcessor',
           ),
           sanitize_keys=None,
           context={'sys.argv': getattr(sys, 'argv', [])[:]},
           tags={},
           sample_rate=1,
           ignore_exceptions=(),
       )
   )


   with entrypoint(raven_sender) as loop:
       loop.run_until_complete(main())

You will find the full specification of options in the `Raven documentation`_.

.. _Raven documentation: https://docs.sentry.io/clients/python/advanced/#client-arguments


``SDWatchdogService``
+++++++++++++++++++++

Ready to use service just adding to your entrypoint and notifying SystemD
service watchdog timer.

This can be safely added at any time, since if the service does not detect
systemd-related environment variables, then its initialization is skipped.

Example of python file:

.. code-block:: python
    :name: test_sdwatchdog

    import logging
    from time import sleep

    from aiomisc import entrypoint
    from aiomisc.service.sdwatchdog import SDWatchdogService


    if __name__ == '__main__':
        with entrypoint(SDWatchdogService()) as loop:
            pass


Example of systemd service file:

.. code-block:: ini

    [Service]
    # Activating the notification mechanism
    Type=notify

    # Command which should be started
    ExecStart=/home/mosquito/.venv/aiomisc/bin/python /home/mosquito/scratch.py

    # The time for which the program must send a watchdog notification
    WatchdogSec=5

    # Kill the process if it has stopped responding to the watchdog timer
    WatchdogSignal=SIGKILL

    # The service should be restarted on failure
    Restart=on-failure

    # Try to kill the process instead of cgroup
    KillMode=process

    # Trying to stop service properly
    KillSignal=SIGINT

    # Trying to restart service properly
    RestartKillSignal=SIGINT

    # Send SIGKILL when timeouts are exceeded
    FinalKillSignal=SIGKILL
    SendSIGKILL=yes


.. _process-service:

``ProcessService``
++++++++++++++++++

A base class for launching a function by a separate system process,
and by termination when the parent process is stopped.

.. code-block:: python

    from typing import Dict, Any

    import aiomisc.service

    # Fictional miner implementation
    from .my_miner import Miner


    class MiningService(aiomisc.service.ProcessService):
        bitcoin: bool = False
        monero: bool = False
        dogiecoin: bool = False

        def in_process(self) -> Any:
            if self.bitcoin:
                miner = Miner(kind="bitcoin")
            elif self.monero:
                miner = Miner(kind="monero")
            elif self.dogiecoin:
                miner = Miner(kind="dogiecoin")
            else:
                # Nothing to do
                return

            miner.do_mining()


    services = [
        MiningService(bitcoin=True),
        MiningService(monero=True),
        MiningService(dogiecoin=True),
    ]

    if __name__ == '__main__':
        with aiomisc.entrypoint(*services) as loop:
            loop.run_forever()


``RespawningProcessService``
++++++++++++++++++++++++++++

A base class for launching a function by a separate system process,
and by termination when the parent process is stopped, It's pretty
like `ProcessService` but have one difference when the process
unexpectedly exited this will be respawned.

.. code-block:: python

    import logging
    from typing import Any

    import aiomisc

    from time import sleep


    class SuicideService(aiomisc.service.RespawningProcessService):
        def in_process(self) -> Any:
            sleep(10)
            logging.warning("Goodbye mad world")
            exit(42)


    if __name__ == '__main__':
        with aiomisc.entrypoint(SuicideService()) as loop:
            loop.run_forever()
