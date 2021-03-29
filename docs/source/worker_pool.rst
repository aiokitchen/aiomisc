Worker Pool
===========

Python has multiprocessing module with Pool class which implements
multiprocess worker pool. The IPC in this case use completely
synchronous communication method. This module reimplement the process based
worker pool but IPC is completely asynchronous on callee side, but workers
in separate processes no asynchronous.

Example
+++++++

This very be useful when you want to process data in separate process but
the input and result data are not big. For example parallel image processing.
Lets write the program which accepts JPEG images and creates thumbnails
for this. In this case you have the file with original image and you have
to generate the output path for ``thumbnail`` function.

.. note::

    You have to install Pollow image processing library for run this example.

    Installing pillow with pip:

    .. code-block::

        pip install Pillow

.. code-block:: python

    # RUN BEFORE: pip install Pillow
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

