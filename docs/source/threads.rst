Working with threads
====================

Wraps blocking function and run it in
the different thread or thread pool.

``contextvars`` support
+++++++++++++++++++++++

All following decorators and functions support ``contextvars`` module,
from PyPI for python earlier 3.7 and builtin a standard library for python 3.7.

.. code-block:: python

    import asyncio
    import aiomisc
    import contextvars
    import random
    import struct


    user_id = contextvars.ContextVar("user_id")

    record_struct = struct.Struct(">I")


    @aiomisc.threaded
    def write_user():
        with open("/tmp/audit.bin", 'ab') as fp:
            fp.write(record_struct.pack(user_id.get()))


    @aiomisc.threaded
    def read_log():
        with open("/tmp/audit.bin", "rb") as fp:
            for chunk in iter(lambda: fp.read(record_struct.size), b''):
                yield record_struct.unpack(chunk)[0]


    async def main():
        futures = []
        for _ in range(5):
            user_id.set(random.randint(1, 65535))
            futures.append(write_user())

        await asyncio.gather(*futures)

        async for data in read_log():
            print(data)


    if __name__ == '__main__':
        with aiomisc.entrypoint() as loop:
            loop.run_until_complete(main())


Example output:

.. code-block::

    6621
    33012
    1590
    45008
    56844


.. note::

    ``contextvars`` has different use cases then ``Context`` class.
    ``contextvars``are applicable for passing context variables through the
    execution stack but created task can not change parent context variables
    because ``contextvars``create lightweight copy. ``Context`` class
    allows it because does not copy context variables.


``@aiomisc.threaded``
+++++++++++++++++++++

Wraps blocking function and run it in the current thread pool.
Decorator returns a :class:`aiomisc.thread_pool.Threaded` object.

This you can call wrapped function as a coroutine using :func:`aiomisc.thread_pool.Threaded.__call__` method
or :func:`aiomisc.thread_pool.Threaded.async_call` method, both returns a coroutine object.
Also you can use it as synchronous function with :func:`aiomisc.thread_pool.Threaded.sync_call` method.


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

        # You can call it as synchronous function
        blocking_function.sync_call()

In case the function is a generator function ``@threaded`` decorator will return
``IteratorWrapper`` (see Threaded generator decorator).


``@aiomisc.threaded_separate``
++++++++++++++++++++++++++++++

Wraps blocking function and run it in a new separate thread.
Highly recommended for long background tasks:

.. code-block:: python

    import asyncio
    import time
    import threading
    import aiomisc


    @aiomisc.threaded
    def blocking_function():
        time.sleep(1)


    @aiomisc.threaded_separate
    def long_blocking_function(event: threading.Event):
        while not event.is_set():
            print("Running")
            time.sleep(1)
        print("Exitting")


    async def main():
        stop_event = threading.Event()

        loop = asyncio.get_event_loop()
        loop.call_later(10, stop_event.set)

        # Running in parallel
        await asyncio.gather(
            blocking_function(),
            # New thread will be spawned
            long_blocking_function(stop_event),
        )


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


Threaded iterator decorator
+++++++++++++++++++++++++++

Wraps blocking generator function and run it in the current thread pool or
on a new separate thread.

Following example reads itself file, chains hashes of every line with
the hash of the previous line and sends hash and content via TCP:

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


    with aiomisc.entrypoint() as loop
        loop.run_until_complete(main())



Run ``netcat`` listener in the terminal and run this example

.. code-block::

    $ netcat -v -l -p 2233
    Connection from 127.0.0.1:54734
    dc80feba2326979f8976e387fbbc8121   import asyncio
    78ec3bcb1c441614ede4af5e5b28f638   import hashlib
    b7df4a0a4eac401b2f835447e5fc4139
    f0a94eb3d7ad23d96846c8cb5e327454   import aiomisc
    0c05dde8ac593bad97235e6ae410cb58
    e4d639552b78adea6b7c928c5ebe2b67   # My first blockchain
    5f04aef64f4cacce39170142fe45e53e
    c0019130ba5210b15db378caf7e9f1c9   @aiomisc.threaded_iterable
    a720db7e706d10f55431a921cdc1cd4c   def blocking_reader(fname):
    0895d7ca2984ea23228b7d653d0b38f2       with open(fname, "r+") as fp:
    0feca8542916af0b130b2d68ade679cf           md5_hash = hashlib.md5()
    4a9ddfea3a0344cadd7a80a8b99ff85c           for line in fp:
    f66fa1df3d60b7ac8991244455dff4ee               bytes_line = line.encode()
    aaac23a5aa34e0f5c448a8d7e973f036               md5_hash.update(bytes_line)
    2040bcaab6137b60e51ae6bd1e279546               yield bytes_line, md5_hash.hexdigest().encode()
    7346740fdcde6f07d42ecd2d6841d483
    14dfb2bae89fa0d7f9b6cba2b39122c4
    d69cc5fe0779f0fa800c6ec0e2a7cbbd   async def main():
    ead8ef1571e6b4727dcd9096a3ade4da       reader, writer = await asyncio.open_connection("127.0.0.1", 2233)
    275eb71a6b6fb219feaa5dc2391f47b7       async with blocking_reader(__file__) as gen:
    110375ba7e8ab3716fd38a6ae8ec8b83           async for line, digest in gen:
    c26894b38440dbdc31f77765f014f445               writer.write(digest)
    27659596bd880c55e2bc72b331dea948               writer.write(b'\t')
    8bb9e27b43a9983c9621c6c5139a822e               writer.write(line)
    2659fbe434899fc66153decf126fdb1c               await writer.drain()
    6815f69821da8e1fad1d60ac44ef501e
    5acc73f7a490dcc3b805e75fb2534254
    0f29ad9505d1f5e205b0cbfef572ab0e   if __name__ == '__main__':
    8b04db9d80d8cda79c3b9c4640c08928       loop = aiomisc.new_event_loop()
    9cc5f29f81e15cb262a46cf96b8788ba       loop.run_until_complete(main())


You should use async context managers in the case when your generator works
infinity, or you have to await the ``.close()`` method when you avoid context managers.

.. code-block:: python

    import asyncio
    import aiomisc


    # Set 2 chunk buffer
    @aiomisc.threaded_iterable(max_size=2)
    def urandom_reader():
        with open('/dev/urandom', "rb") as fp:
            while True:
                yield fp.read(8)


    # Infinity buffer on a separate thread
    @aiomisc.threaded_iterable_separate
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


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())

``aiomisc.IteratorWrapper``
+++++++++++++++++++++++++++

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

``aiomisc.IteratorWrapperSeparate``
+++++++++++++++++++++++++++++++++++

Run iterables on a separate thread:

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
        wrapper = aiomisc.IteratorWrapperSeparate(
            urandom_reader, max_size=2
        )

        async with wrapper as gen:
            md5_hash = hashlib.md5(b'')
            counter = 0
            async for item in gen:
                md5_hash.update(item)
                counter += 1

                if counter >= 100:
                    break

        print(md5_hash.hexdigest())


    if __name__ == '__main__':
        with aiomisc.entrypoint() as loop:
            loop.run_until_complete(main())



``aiomisc.ThreadPoolExecutor``
++++++++++++++++++++++++++++++

This is a fast thread pool implementation.

Setting as a default thread pool:

.. code-block:: python

    import asyncio
    from aiomisc import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    thread_pool = ThreadPoolExecutor(4)
    loop.set_default_executor(thread_pool)


.. note::

    ``entrypoint`` context manager will set it by default.

    ``entrypoint``'s argument ``pool_size`` limits thread pool size.


``aiomisc.sync_wait_coroutine``
+++++++++++++++++++++++++++++++

Functions running in thread can't call and wait for a result from coroutines
by default. This function is the helper for send coroutine to the event loop
and waits for it in the current thread.

.. code-block:: python

    import asyncio
    import aiomisc


    async def coro():
        print("Coroutine started")
        await asyncio.sleep(1)
        print("Coroutine done")


    @aiomisc.threaded
    def in_thread(loop):
        print("Thread started")
        aiomisc.sync_wait_coroutine(loop, coro)
        print("Thread finished")


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(in_thread(loop))
