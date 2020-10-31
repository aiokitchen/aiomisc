asynchronous file operations
============================

Asynchronous files operations. Based on thread-pool under the hood.

.. code-block:: python

    import aiomisc


    async def file_write():
        async with aiomisc.io.async_open('/tmp/test.txt', 'w+') as afp:
            await afp.write("Hello")
            await afp.write(" ")
            await afp.write("world")

            await afp.seek(0)
            print(await afp.read())
