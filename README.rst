aiomisc - miscellaneous utils for asyncio
=========================================

.. image:: https://coveralls.io/repos/github/mosquito/aiomisc/badge.svg?branch=master
   :target: https://coveralls.io/github/mosquito/aiomisc
   :alt: Coveralls

.. image:: https://cloud.drone.io/api/badges/mosquito/aiomisc/status.svg
   :target: https://cloud.drone.io/mosquito/aiomisc
   :alt: Drone CI

.. image:: https://img.shields.io/pypi/v/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/
   :alt: Latest Version

.. image:: https://img.shields.io/pypi/wheel/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/pyversions/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/l/aiomisc.svg
   :target: https://pypi.python.org/pypi/aiomisc/


Miscellaneous utils for asyncio.

.. contents:: Table of contents

Installation
------------

Installing from pypi:

.. code-block:: bash

    pip3 install aiomisc


Installing from github.com:

.. code-block:: bash

    pip3 install git+https://github.com/mosquito/aiomisc.git


Quick Start
-----------

Async entrypoint with logging and useful arguments:

.. code-block:: python

    import argparse
    import asyncio
    import os
    import logging

    from aiomisc.entrypoint import entrypoint, LogFormat


    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-L", "--log-level", help="Log level",
        default=os.getenv('LOG_LEVEL', 'info'),
        choices=(
            'critical', 'fatal', 'error', 'warning',
            'warn', 'info', 'debug', 'notset'
        ),
    )

    parser.add_argument(
        "--log-format", help="Log format",
        default=os.getenv('LOG_FORMAT', 'color'),
        choices=LogFormat.choices(),
        metavar='LOG_FORMAT',
    )

    parser.add_argument(
        "-D", "--debug", action='store_true',
        help="Run loop and application in debug mode"
    )


    parser.add_argument(
        "--pool-size", help="Thread pool size",
        default=os.getenv('THREAD_POOL'), type=int,
    )


    log = logging.getLogger(__name__)


    async def main():
        log.info('Starting')
        await asyncio.sleep(3)
        log.info('Exiting')


    if __name__ == '__main__':
        arg = parser.parse_args()

        with entrypoint(log_level=arg.log_level,
                        log_format=arg.log_format) as loop:
            loop.run_until_complete(main())


Install event loop on program start:

.. code-block:: python

    import asyncio
    from aiomisc.utils import new_event_loop


    # Installing uvloop event loop
    # and set `aiomisc.thread_pool.ThreadPoolExecutor`
    # as default executor
    new_event_loop()


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())


Close current event loop and install a new one:

.. code-block:: python

    import asyncio
    from aiomisc.utils import new_event_loop


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = new_event_loop()
        loop.run_until_complete(main())

Overview:
---------

entrypoint
++++++++++

In generic case the entrypoint helper creates event loop and cancels already
running coroutines on exit.

.. code-block:: python

    import asyncio
    from aiomisc.entrypoint import entrypoint

    async def main():
        await asyncio.sleep(1)

    with entrypoint() as loop:
        loop.run_until_complete(main())


Services
++++++++

Services is an abstractions helping organize many tasks on one process. Each service must implement ``start()`` method and ``stop()`` method (optional).

Service should be passed to the entrypoint, and will be started after an event loop creates.

.. warning ::

   Never use ``asyncio.get_event_loop()`` in ``start()`` method.
   Running event loop will be set before ``start()`` calls.

   Use ``self.loop`` instead:

   .. code-block:: python

      from aiomisc.service import Service
      from aiomisc.entrypoint import entrypoint


      class MyService(Service):
        async def start(self):
            await asyncio.sleep(3600, loop=self.loop)


      with entrypoint(MyService()) as loop:
          loop.run_forever()


This package contains some useful base classes for simple service writing.

TCPServer
*********

``TCPServer`` - it's a base class for writing TCP servers.
Just implement ``handle_client(reader, writer)`` for use it.

.. code-block:: python

    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())


    with entrypoint(EchoServer(address='::1', port=8901)) as loop:
        loop.run_forever()


UDPServer
*********

``UDPServer`` - it's a base class for writing UDP servers.
Just implement ``handle_datagram(data, addr)`` for use it.

.. code-block:: python

    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    with entrypoint(UDPPrinter(address='::1', port=3000)) as loop:
        loop.run_forever()


TLSServer
*********

it's a base class for writing TCP servers with TLS.
Just implement ``handle_client(reader, writer)`` for use it.

.. code-block:: python

    class SecureEchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())

    service = SecureEchoServer(
        address='::1',
        port=8900,
        ca='ca.pem',
        cert='cert.pem',
        key='key.pem',
        verify=False,
    )

    with entrypoint(service) as loop:
        loop.run_forever()


Multiple services
*****************

You can pass service instances to the entrypoint for running them,
after exiting context manager service instances will be gracefully shut down.

.. code-block:: python

    import asyncio
    from aiomisc.entrypoint import entrypoint
    from aiomisc.service import Service, TCPServer, UDPServer


    class LoggingService(Service):
        async def start(self):
            while True:
                print('Hello from service', self.name)
                await asyncio.sleep(1)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())


    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    services = (
        LoggingService(name='#1'),
        EchoServer(address='::1', port=8901),
        UDPPrinter(address='::1', port=3000),
    )


    with entrypoint(*services) as loop:
        loop.run_forever()


Configuration
*************

``Service`` metaclass accepts all kwargs and will set it to the
``self`` as an attributes.

.. code-block:: python

    import asyncio
    from aiomisc.entrypoint import entrypoint
    from aiomisc.service import Service, TCPServer, UDPServer


    class LoggingService(Service):
        # required kwargs
        __required__ = frozenset({'name'})

        # default value
        delay: int = 1

        async def start(self):
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


Context
*******

Services might be required data for each other.
In this case you should use ``Context``.

``Context`` is the repository associated with the running entrypoint.

``Context``-object will be creating in entrypoint and links
to the running event loop.

Cross dependent services might wait data or might set data for each other
via the context.

For service instances ``self.context`` available since entrypoint starts.
For other cases ``get_context()`` function returns current context.


.. code-block:: python

    import asyncio
    from random import random, randint

    from aiomisc.entrypoint import entrypoint, get_context
    from aiomisc.service import Service


    class LoggingService(Service):
        async def start(self):
            context = get_context()

            wait_time = await context['wait_time']

            print('Wait time is', wait_time)
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
        loop.run_forever()


.. note ::

    Do not use this too often. In base case service might be configured
    using passing kwargs to the service instance.


aiohttp service
***************

.. warning ::

   requires installed aiohttp:

   .. code-block::

       pip install aiohttp

   or using extras:

   .. code-block::

       pip install aiomisc[aiohttp]


aiohttp application might be started as a serivce

.. code-block:: python

    import aiohttp.web
    import argparse
    from aiomisc.entrypoint import entrypoint
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


Class ``AIOHTTPSSLService`` is the same then ``AIOHTTPService`` but
creates HTTPS server. You must pass ssl required options
(see ``TLSServer`` class).


timeout decorator
+++++++++++++++++

Decorator that guarantee maximum execution time for decorated function.

.. code-block:: python

    from aiomisc.timeout import timeout

    @timeout(1)
    async def bad_func():
        await asyncio.sleep(2)


Async backoff
+++++++++++++

Decorator that ensures that the decorated function will be successfully
completed in ``waterline`` time at best case,  or will be retried
until ``deadline`` time expires.


.. code-block:: python

    from aiomisc.backoff import asyncbackoff

    waterline = 0.1
    deadline = 1
    pause = 0.1

    @asyncbackoff(waterline, deadline, pause)
    async def db_fetch():
        ...


    @asyncbackoff(0.1, 1, 0.1)
    async def db_save(data: dict):
        ...


asynchronous file operations
++++++++++++++++++++++++++++

Asynchronous files operations. Based on thread-pool under the hood.

.. code-block:: python

    from aiomisc.io import async_open


    async def db_fetch():
        async with async_open('/tmp/test.txt', 'w+') as afp:
            await afp.write("Hello")
            await afp.write(" ")
            await afp.write("world")

            await afp.seek(0)
            print(await afp.read())


Threaded decorator
++++++++++++++++++

Wraps blocking function and run it in the thread pool.


.. code-block:: python

    import asyncio
    import time
    from aiomisc.utils import new_event_loop
    from aiomisc.thread_pool import threaded


    @threaded
    def blocking_function():
        time.sleep(1)


    async def main():
        # Running in parallel
        await asyncio.gather(
            blocking_function(),
            blocking_function(),
        )


    if __name__ == '__main__':
        loop = new_event_loop()
        loop.run_until_complete(main())


Fast ThreadPoolExecutor
+++++++++++++++++++++++

This is a simple thread pool implementation.

Installation as a default thread pool:

.. code-block:: python

    import asyncio
    from aiomisc.thread_pool import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    thread_pool = ThreadPoolExecutor(4, loop=loop)
    loop.set_default_executor(thread_pool)


Bind socket
+++++++++++

.. code-block:: python

    from aiomisc.utils import bind_socket

    # IPv4 socket
    sock = bind_socket(address="127.0.0.1", port=1234)

    # IPv6 socket (on Linux IPv4 socket will be bind too)
    sock = bind_socket(address="::1", port=1234)


Periodic callback
+++++++++++++++++

Runs coroutine function periodically

.. code-block:: python

    import asyncio
    import time
    from aiomisc.utils import new_event_loop
    from aiomisc.periodic import PeriodicCallback


    async def periodic_function():
        print("Hello")


    if __name__ == '__main__':
        loop = new_event_loop()

        periodic = PeriodicCallback(periodic_function)

        # Call it each second
        periodic.start(1)

        loop.run_forever()


Logging configuration
+++++++++++++++++++++

Setting up colorized logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='color')

Setting up json logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='json')


Buffered log handler
********************

Parameter `buffered=True` enables memory buffer that flushes
logs into a thread.

.. code-block:: python

    import logging
    from aiomisc.log import basic_config
    from aiomisc.periodic import PeriodicCallback
    from aiomisc.utils import new_event_loop


    # Configure logging globally
    basic_config(level=logging.INFO, buffered=False, log_format='json')

    async def write_log(loop):
        logging.info("Hello %f", loop.time())

    if __name__ == '__main__':
        loop = new_event_loop()

        # Configure
        basic_config(
            level=logging.INFO,
            buffered=True,
            log_format='color',
            flush_interval=2
        )

        periodic = PeriodicCallback(write_log, loop)
        periodic.start(0.3)

        loop.run_forever()


Useful services
---------------

Memory Tracer
+++++++++++++

Simple and useful service for logging largest python
objects allocated in memory.


.. code-block:: python

    import asyncio
    import os
    from aiomisc.entrypoint import entrypoint
    from aiomisc.service import MemoryTracer


    async def main():
        leaking = []

        while True:
            leaking.append(os.urandom(128))
            await asyncio.sleep(0)


    with entrypoint(MemoryTracer(interval=1, top_results=5)) as loop:
        loop.run_until_complete(main())


This example will log something like this each second.

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


Versioning
----------

This software follows `Semantic Versioning`_


How to develop?
---------------

Should be installed:

* `virtualenv`
* GNU Make as `make`
* Python 3.5+ as `python3`


For setting up developer environment just type

    .. code-block::

        make develop


.. _Semantic Versioning: http://semver.org/
