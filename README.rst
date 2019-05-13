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

With uvloop_:

.. code-block:: bash

    pip3 install "aiomisc[uvloop]"


With aiohttp_:

.. code-block:: bash

    pip3 install "aiomisc[aiohttp]"


Installing from github.com:

.. code-block:: bash

    pip3 install git+https://github.com/mosquito/aiomisc.git


.. _uvloop: https://pypi.org/project/uvloop
.. _aiohttp: https://pypi.org/project/aiohttp


Quick Start
-----------

Async entrypoint with logging and useful arguments:

.. code-block:: python

    import argparse
    import asyncio
    import os
    import logging

    from aiomisc import entrypoint


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
        choices=aiomisc.log.LogFormat.choices(),
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
    import aiomisc


    # Installing uvloop event loop
    # and set `aiomisc.thread_pool.ThreadPoolExecutor`
    # as default executor
    aiomisc.new_event_loop()


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())


Close current event loop and install a new one:

.. code-block:: python

    import asyncio
    import aiomisc


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = aiomisc.new_event_loop()
        loop.run_until_complete(main())

Overview:
---------

entrypoint
++++++++++

In generic case the entrypoint helper creates event loop and cancels already
running coroutines on exit.

.. code-block:: python

    import asyncio
    import aiomisc

    async def main():
        await asyncio.sleep(1)

    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


Services
++++++++

``Services`` is abstraction to help organize lots of different
tasks in one process. Each service must implement ``start()`` method and can
implement ``stop()`` method.

Service instance should be passed to the ``entrypoint``, and will be started
after event loop has been created.

.. note::

   Current event-loop will be set before ``start()`` method called.
   The event loop will be set as current for this thread.

   Please avoid using ``asyncio.get_event_loop()`` explicitly inside
   ``start()`` method. Use ``self.loop`` instead:

   .. code-block:: python

      from aiomisc import entrypoint, Service


      class MyService(Service):
        async def start(self):
            # Send signal to entrypoint for continue running
            self.start_event.set()

            # Start service task
            await asyncio.sleep(3600, loop=self.loop)


      with entrypoint(MyService()) as loop:
          loop.run_forever()


Method ``start()`` creates as a separate task that can run forever. But in
this case ``self.start_event.set()`` should be called for notifying
``entrypoint``.

During graceful shutdown method ``stop()`` will be called first,
and after that all running tasks will be cancelled (including ``start()``).


This package contains some useful base classes for simple services writing.

TCPServer
*********

``TCPServer`` - it's a base class for writing TCP servers.
Just implement ``handle_client(reader, writer)`` to use it.

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
Just implement ``handle_datagram(data, addr)`` to use it.

.. code-block:: python

    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    with entrypoint(UDPPrinter(address='::1', port=3000)) as loop:
        loop.run_forever()


TLSServer
*********

TLSServer - it's a base class for writing TCP servers with TLS.
Just implement ``handle_client(reader, writer)`` to use it.

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

Pass several service instances to the ``entrypoint`` to run all of them.
After exiting the entrypoint service instances will be gracefully shut down.

.. code-block:: python

    import asyncio
    from aiomisc import entrypoint
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

Services can require each others data. In this case you should use ``Context``.

``Context`` is a repository associated with the running ``entrypoint``.

``Context``-object will be created when ``entrypoint`` starts and linked
to the running event loop.

Cross dependent services might await or set each others data via the context.

For service instances ``self.context`` is available since ``entrypoint``
started. In other cases ``get_context()`` function returns current context.


.. code-block:: python

    import asyncio
    from random import random, randint

    from aiomisc import entrypoint, get_context, Service


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


.. note::

    It's not a silver bullet. In base case services can be configured by
    passing kwargs to the service ``__init__`` method.


aiohttp service
***************

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


Class ``AIOHTTPSSLService`` is similar to ``AIOHTTPService`` but creates HTTPS
server. You must pass SSL-required options (see ``TLSServer`` class).

Memory Tracer
*************

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


timeout decorator
+++++++++++++++++

Decorator that ensures the execution time limit for decorated function is met.

.. code-block:: python

    from aiomisc import timeout

    @timeout(1)
    async def bad_func():
        await asyncio.sleep(2)


Async backoff
+++++++++++++

Abstraction:

* ``attempt_timeout`` is maximum execution time for one execution attempt.
* ``deadline`` is maximum execution time for all execution attempts.
* ``pause`` is time gap between execution attempts.
* ``exceptions`` retrying when this exceptions was raised.

Decorator that ensures that ``attempt_timeout`` and ``deadline`` time
limits are met by decorated function.

In case of exception function will be called again with similar arguments after
``pause`` seconds.


Position arguments notation:

.. code-block:: python

    from aiomisc import asyncbackoff

    attempt_timeout = 0.1
    deadline = 1
    pause = 0.1

    @asyncbackoff(attempt_timeout, deadline, pause)
    async def db_fetch():
        ...


    @asyncbackoff(0.1, 1, 0.1)
    async def db_save(data: dict):
        ...


    # Passing exceptions for handling
    @asyncbackoff(0.1, 1, 0.1, TypeError, RuntimeError, ValueError)
    async def db_fetch(data: dict):
        ...


Keyword arguments notation:

.. code-block:: python

    from aiomisc import asyncbackoff

    attempt_timeout = 0.1
    deadline = 1
    pause = 0.1

    @asyncbackoff(attempt_timeout=attempt_timeout,
                  deadline=deadline, pause=pause)
    async def db_fetch():
        ...


    @asyncbackoff(attempt_timeout=0.1, deadline=1, pause=0.1)
    async def db_save(data: dict):
        ...


    # Passing exceptions for handling
    @asyncbackoff(attempt_timeout=0.1, deadline=1, pause=0.1,
                  exceptions=[TypeError, RuntimeError, ValueError])
    async def db_fetch(data: dict):
        ...



asynchronous file operations
++++++++++++++++++++++++++++

Asynchronous files operations. Based on thread-pool under the hood.

.. code-block:: python

    import aiomisc


    async def db_fetch():
        async with aiomisc.io.async_open('/tmp/test.txt', 'w+') as afp:
            await afp.write("Hello")
            await afp.write(" ")
            await afp.write("world")

            await afp.seek(0)
            print(await afp.read())


Threaded decorator
++++++++++++++++++

Wraps blocking function and runs it in the current thread pool.


.. code-block:: python

    import asyncio
    import time
    from aiomisc import new_event_loop, threaded


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

In case function is a generator function ``@threaded`` decorator will return
``IteratorWrapper`` (see Threaded generator decorator).


Threaded generator decorator
++++++++++++++++++++++++++++

Wraps blocking generator function and runs it in the current thread pool.

Following example reads itself file, chains hashes of every line with
hash of previous line and sends hash and content via TCP:

.. code-block:: python

    import asyncio
    import hashlib

    import aiomisc

    # My first blockchain

    @aiomisc.threaded_iterable
    def blocking_reader(fname):
        with open(fname, "r+") as fp:
            md5_hash = hashlib.md5()
            for line in fp:
                bytes_line = line.encode()
                md5_hash.update(bytes_line)
                yield bytes_line, md5_hash.hexdigest().encode()


    async def main():
        reader, writer = await asyncio.open_connection("127.0.0.1", 2233)
        async with blocking_reader(__file__) as gen:
            async for line, digest in gen:
                writer.write(digest)
                writer.write(b'\t')
                writer.write(line)
                await writer.drain()


    if __name__ == '__main__':
        loop = aiomisc.new_event_loop()
        loop.run_until_complete(main())



Run ``netcat`` listener in the terminal and run this example

.. code-block::

    $ netcat -v -l -p 2233
    Connection from 127.0.0.1:54734
    dc80feba2326979f8976e387fbbc8121	import asyncio
    78ec3bcb1c441614ede4af5e5b28f638	import hashlib
    b7df4a0a4eac401b2f835447e5fc4139
    f0a94eb3d7ad23d96846c8cb5e327454	import aiomisc
    0c05dde8ac593bad97235e6ae410cb58
    e4d639552b78adea6b7c928c5ebe2b67	# My first blockchain
    5f04aef64f4cacce39170142fe45e53e
    c0019130ba5210b15db378caf7e9f1c9	@aiomisc.threaded_iterable
    a720db7e706d10f55431a921cdc1cd4c	def blocking_reader(fname):
    0895d7ca2984ea23228b7d653d0b38f2	    with open(fname, "r+") as fp:
    0feca8542916af0b130b2d68ade679cf	        md5_hash = hashlib.md5()
    4a9ddfea3a0344cadd7a80a8b99ff85c	        for line in fp:
    f66fa1df3d60b7ac8991244455dff4ee	            bytes_line = line.encode()
    aaac23a5aa34e0f5c448a8d7e973f036	            md5_hash.update(bytes_line)
    2040bcaab6137b60e51ae6bd1e279546	            yield bytes_line, md5_hash.hexdigest().encode()
    7346740fdcde6f07d42ecd2d6841d483
    14dfb2bae89fa0d7f9b6cba2b39122c4
    d69cc5fe0779f0fa800c6ec0e2a7cbbd	async def main():
    ead8ef1571e6b4727dcd9096a3ade4da	    reader, writer = await asyncio.open_connection("127.0.0.1", 2233)
    275eb71a6b6fb219feaa5dc2391f47b7	    async with blocking_reader(__file__) as gen:
    110375ba7e8ab3716fd38a6ae8ec8b83	        async for line, digest in gen:
    c26894b38440dbdc31f77765f014f445	            writer.write(digest)
    27659596bd880c55e2bc72b331dea948	            writer.write(b'\t')
    8bb9e27b43a9983c9621c6c5139a822e	            writer.write(line)
    2659fbe434899fc66153decf126fdb1c	            await writer.drain()
    6815f69821da8e1fad1d60ac44ef501e
    5acc73f7a490dcc3b805e75fb2534254
    0f29ad9505d1f5e205b0cbfef572ab0e	if __name__ == '__main__':
    8b04db9d80d8cda79c3b9c4640c08928	    loop = aiomisc.new_event_loop()
    9cc5f29f81e15cb262a46cf96b8788ba	    loop.run_until_complete(main())


You should use async context managers in case when your generator works
infinity, or you have to await the ``.close()`` method when you avoid context managers.

.. code-block:: python

    import asyncio
    from aiomisc import new_event_loop, threaded_iterable


    # Set 2 chunk buffer
    @threaded_iterable(max_size=2)
    def urandom_reader():
        with open('/dev/urandom', "rb") as fp:
            while True:
                yield fp.read(8)


    # Infinity buffer
    @threaded_iterable
    def blocking_reader(fname):
        with open(fname, "r") as fp:
            yield from fp


    async def main():
        reader, writer = await asyncio.open_connection("127.0.0.1", 2233)
        async for line in blocking_reader(__file__):
            writer.write(line.encode())

        await writer.drain()

        # Feed white noise
        gen = urandom_reader()
        counter = 0
        async for line in gen:
            writer.write(line)
            counter += 1

            if counter == 10:
                break

        await writer.drain()

        # Stop running generator
        await gen.close()

        # Using context manager
        async with urandom_reader() as gen:
            counter = 0
            async for line in gen:
                writer.write(line)
                counter += 1

                if counter == 10:
                    break

        await writer.drain()

    if __name__ == '__main__':
        loop = new_event_loop()
        loop.run_until_complete(main())


Run iterables on dedicated thread pool:

.. code-block:: python

    import concurrent.futures
    import hashlib
    import aiomisc


    def urandom_reader():
        with open('/dev/urandom', "rb") as fp:
            while True:
                yield fp.read(1024)


    async def main():
        # create a new thread pool
        pool = concurrent.futures.ThreadPoolExecutor(1)
        wrapper = aiomisc.IteratorWrapper(
            urandom_reader,
            executor=pool,
            max_size=2
        )

        async with wrapper as gen:
            md5_hash = hashlib.md5(b'')
            counter = 0
            async for item in gen:
                md5_hash.update(item)
                counter += 1

                if counter >= 100:
                    break

        pool.shutdown()
        print(md5_hash.hexdigest())


    if __name__ == '__main__':
        with aiomisc.entrypoint() as loop:
            loop.run_until_complete(main())



Fast ThreadPoolExecutor
+++++++++++++++++++++++

This is a simple thread pool implementation.

Setting as a default thread pool:

.. code-block:: python

    import asyncio
    from aiomisc import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    thread_pool = ThreadPoolExecutor(4, loop=loop)
    loop.set_default_executor(thread_pool)


.. note::

    ``entrypoint`` context manager will set it by default.

    ``entrypoint``'s argument ``pool_size`` limits thread pool size.


Select
++++++

In some cases you should wait only one of multiple tasks. ``select``
waits first passed awaitable object and returns list of results.

.. code-block:: python

    import asyncio
    import aiomisc


    async def main():
        loop = asyncio.get_event_loop()
        event = asyncio.Event()
        future = asyncio.Future()

        loop.call_soon(event.set)

        await aiomisc.select(event.wait(), future)
        print(event.is_set())       # True

        event = asyncio.Event()
        future = asyncio.Future()

        loop.call_soon(future.set_result, True)

        results = await aiomisc.select(future, event.wait())
        future_result, event_result = results

        print(results.result())             # True
        print(results.result_idx)           # 0
        print(event_result, future_result)  # None, True


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


.. warning::

    When you don't want to cancel pending tasks pass ``cancel=False`` argument.
    In this case you have to handle task completion manually or get warnings.


Signal
++++++

You can register async callback functions for specific events of an entrypoint.

pre_start
*********

``pre_start`` signal occurs on entrypoint start up before any service have started.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.PRE_START)
    async def prepare_database(entrypoint, services):
      ...

    with entrypoint() as loop:
        loop.run_forever()


post_stop
*********

``post_stop`` signal occurs on entrypoint shutdown after all services have been
stopped.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.POST_STOP)
    async def cleanup(entrypoint):
      ...

    with entrypoint() as loop:
        loop.run_forever()


Plugins
+++++++

aiomisc can be extended with plugins as separate packages. Plugins can
enhance aiomisc by mean of signals_.

.. _signals: #signal

In order to make your plugin discoverable by aiomisc you should add
``aiomisc.plugins`` entry to entry to ``entry_points`` argument of ``setup``
call in ``setup.py`` of a plugin.

.. code-block:: python

    # setup.py

    setup(
        # ...
        entry_points={
            "aiomisc.plugins": ["myplugin = aiomisc_myplugin.plugin"]
        },
        # ...
    )


Modules which provided in ``entry_points`` should have ``setup`` function.
This functions would be called by aiomisc and must contain signals connecting.

.. code-block:: python

    async def hello(entrypoint, services):
        print('Hello from aiomisc plugin')


    def setup():
        from aiomisc import entrypoint

        entrypoint.PRE_START.connect(hello)


Bind socket
+++++++++++

Bind socket and set ``setblocking(False)`` for just created socket.
This detects ``address`` format and select socket family automatically.

.. code-block:: python

    from aiomisc import bind_socket

    # IPv4 socket
    sock = bind_socket(address="127.0.0.1", port=1234)

    # IPv6 socket (on Linux IPv4 socket will be bind too)
    sock = bind_socket(address="::1", port=1234)


Periodic callback
+++++++++++++++++

Runs coroutine function periodically.

.. code-block:: python

    import asyncio
    import time
    from aiomisc import new_event_loop, PeriodicCallback


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

Color
*****

Setting up colorized logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='color')

JSON
****

Setting up json logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='json')


Buffered log handler
********************

Parameter `buffered=True` enables memory buffer that flushes logs in a thread.

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


.. note::

    ``entrypoint`` accepts ``log_format`` parameter for configure it.

    List of all supported log formats is available from
    ``aiomisc.log.LogFormat.choices()``


Pytest plugin
+++++++++++++

This package contains plugin for pytest.

Basic usage
***********

Simple usage example:

.. code-block:: python

    import asyncio
    import pytest


    async def test_sample(loop):
        f = loop.crete_future()
        loop.call_soon(f.set_result, True)

        assert await f


asynchronous fuxture example:


.. code-block:: python

    import asyncio
    import pytest


    @pytest.fixture
    async def my_fixture(loop):
        await asyncio.sleep(0)

        # Requires python 3.6+
        yield


pytest markers
**************

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
***********************

.. code-block:: python

    import pytest


    @pytest.fixture
    def default_context():
        return {
            'foo': 'bar',
            'bar': 'foo',
        }


Testing services
****************

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
****************************

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
**********************

.. code-block:: python

    thread_pool_ids = ('aiomisc pool', 'default pool')
    thread_pool_implementation = (ThreadPoolExecutor,
                                  concurrent.futures.ThreadPoolExecutor)


    @pytest.fixture(params=thread_pool_implementation, ids=thread_pool_ids)
    def thread_pool_executor(request):
        return request.param


entrypoint arguments
********************

.. code-block:: python

    import pytest

    @pytest.fixture
    def entrypoint_kwargs() -> dict:
        return dict(log_config=False)


aiohttp test client
*******************

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
