``WorkerPool``
==============

Python has the ``multiprocessing`` module with ``Pool`` class which
implements a similar worker pool. The IPC in this case uses a completely
synchronous communication method. This module reimplements the process-based
worker pool but IPC is completely asynchronous on the caller side,
meanwhile, workers in separate processes aren't asynchronous.

Example
+++++++

This would be useful when you want to process the data in a separate process,
and the input and output data are not very large. Otherwise, it will work
fine, of course, but you would have to spend time transmitting the data
over IPC.

A good example is parallel image processing. Of course, you can transfer bytes
of images through the IPC of the working pool, but in general, case passing the
file name to the worker will be better. The exception will be cases when the
image payload is significantly smaller the 1KB for example.

Let's write a program that accepts images in JPEG format and creates thumbnails
for this. In this case, you have a file with the original image, and you should
generate the output path for the 'thumbnail' function.

.. note::

    You have to install the Pillow image processing library to run this example.

    Installing pillow with pip:

    .. code-block::

        pip install Pillow

.. code-block:: python

    import asyncio
    import sys
    from multiprocessing import cpu_count
    from typing import Tuple
    from pathlib import Path
    from PIL import Image
    from aiomisc import entrypoint, WorkerPool


    def thumbnail(src_path: str, dest_path: str, box: Tuple[int, int]):
        img = Image.open(src_path)
        img.thumbnail(box)
        img.save(
            dest_path, "JPEG", quality=65,
            optimize=True,
            icc_profile=img.info.get('icc_profile'),
            exif=img.info.get('exif'),
        )
        return img.size


    sizes = [
        (1024, 1024),
        (512, 512),
        (256, 256),
        (128, 128),
        (64, 64),
        (32, 32),
    ]


    async def amain(path: Path):
        # Create directories
        for size in sizes:
            size_dir = "x".join(map(str, size))
            size_path = (path / 'thumbnails' / size_dir)
            size_path.mkdir(parents=True, exist_ok=True)

        # Create and run WorkerPool
        async with WorkerPool(cpu_count()) as pool:
            tasks = []
            for image in path.iterdir():
                if not image.name.endswith(".jpg"):
                    continue

                if image.is_relative_to(path / 'thumbnails'):
                    continue

                for size in sizes:
                    rel_path = image.relative_to(path).parent
                    size_dir = "x".join(map(str, size))
                    dest_path = (
                        path / rel_path /
                        'thumbnails' / size_dir /
                        image.name
                    )

                    tasks.append(
                        pool.create_task(
                            thumbnail,
                            str(image),
                            str(dest_path),
                            size
                        )
                    )

            await asyncio.gather(*tasks)


    if __name__ == '__main__':
        with entrypoint() as loop:
            image_dir = Path(sys.argv[1])
            loop.run_until_complete(amain(image_dir))


This example takes the image directory as the first command-line argument and
creates directories for the thumbnails. After that, a ``WorkerPool`` is started
with as many processes as the processor has cores.

The main process creates tasks for the workers, each task is a conversion of
one file to one size, after which all tasks fall into the ``WorkerPool``
instance.

The ``WorkerPool`` processes the tasks concurrently, but only one job for one
a worker at the same time.
