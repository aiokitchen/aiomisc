asynchronous file operations
============================

Asynchronous files operations including support for data compression on the fly.
Based on the thread pool under the hood.

.. code-block:: python
    :name: test_io

    import aiomisc
    import tempfile
    from pathlib import Path


    async def file_write():
        with tempfile.TemporaryDirectory() as tmp:
            fname = Path(tmp) / 'test.txt'

            # Some tools, such as mypy, will not be able to infer the type
            # from the `async_open` function based on the `b` character passed
            # to the mode.
            # We'll have to tell the type here explicitly.
            afp: aiomisc.io.AsyncTextIO

            async with aiomisc.io.async_open(fname, 'w+') as afp:
                await afp.write("Hello")
                await afp.write(" ")
                await afp.write("world")

                await afp.seek(0)
                print(await afp.read())


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(file_write())


This is the way to working with files based on threads.
It's very similar to `aiofiles`_ project and same limitations.

Of course, you can use `aiofile`_ project for this. But it's not a
silver bullet and has OS API-related limitations.

In general, for light loads, I would advise you to adhere to the following rules:

* If reading and writing small or big chunks from files with random access
  is the main task in your project, use `aiofile`_.
* Otherwise use this module or `aiofiles`_
* If the main task is to read large chunks of files for processing,
  both of the above methods are not optimal cause you will switch
  context each IO operation, it's often suboptimal for file cache
  and you will be lost execution time for context switches. In case
  for thread-based IO executor implementation thread context
  switches cost might be more expensive than IO operation time
  in summary.

  Just try pack all blocking staff in separate functions and
  call it in a thread pool, see the example bellow:

  .. code-block:: python
     :name: test_io_file_threaded

     import os
     import aiomisc
     import hashlib
     import tempfile
     from pathlib import Path


     @aiomisc.threaded
     def hash_file(filename, chunk_size=65535, hash_func=hashlib.blake2b):
         hasher = hash_func()

         with open(filename, "rb") as fp:
             for chunk in iter(lambda: fp.read(chunk_size), b""):
                hasher.update(chunk)

         return hasher.hexdigest()


     @aiomisc.threaded
     def fill_random_file(filename, size, chunk_size=65535):
         with open(filename, "wb") as fp:
            while fp.tell() < size:
                fp.write(os.urandom(chunk_size))

            return fp.tell()


     async def main(path):
         filename = path / "one"
         await fill_random_file(filename, 1024 * 1024)
         first_hash = await hash_file(filename)

         filename = path / "two"
         await fill_random_file(filename, 1024 * 1024)
         second_hash = await hash_file(filename)

         assert first_hash != second_hash


     with tempfile.TemporaryDirectory(prefix="random.") as path:
        aiomisc.run(
            main(Path(path))
        )

In the fly compression
----------------------

To enable compression, you need to pass the `compression` argument to the
`async_open` function.

Supported compressors:

* :class:`aiomisc.io.Compression.NONE`
* :class:`aiomisc.io.Compression.GZIP`
* :class:`aiomisc.io.Compression.BZ2`
* :class:`aiomisc.io.Compression.LZMA`

An example of usage:

.. code-block:: python
    :name: test_compressed_gzip_io

    import tempfile
    from aiomisc import run
    from aiomisc.io import async_open, Compression
    from pathlib import Path


    async def file_write():
        with tempfile.TemporaryDirectory() as tmp:
            fname = Path(tmp) / 'test.txt'

            async with async_open(
                fname, 'w+', compression=Compression.GZIP
            ) as afp:
                for _ in range(10000):
                    await afp.write("Hello World\n")

            file_size = fname.stat().st_size
            assert file_size < 10000, f"File too large {file_size} bytes"

    run(file_write())


.. _aiofiles: https://pypi.org/project/aiofiles/
.. _aiofile: https://pypi.org/project/aiofile/
