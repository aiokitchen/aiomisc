asynchronous file operations
============================

Asynchronous files operations. Based on thread-pool under the hood.

.. code-block:: python
    :name: test_io

    import aiomisc
    import tempfile
    from pathlib import Path


    async def file_write():
        with tempfile.TemporaryDirectory() as tmp:
            fname = Path(tmp) / 'test.txt'

            async with aiomisc.io.async_open(fname, 'w+') as afp:
                await afp.write("Hello")
                await afp.write(" ")
                await afp.write("world")

                await afp.seek(0)
                print(await afp.read())


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(file_write())
