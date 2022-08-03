``ProcessPoolExecutor``
=======================

This is a simple process pool executor implementation.

Example:

.. code-block:: python

    import asyncio
    import time
    import os
    from aiomisc import ProcessPoolExecutor

    def process_inner():
        for _ in range(10):
            print(os.getpid())
            time.sleep(1)

        return os.getpid()


    loop = asyncio.get_event_loop()
    process_pool = ProcessPoolExecutor(4)


    async def main():
        print(
            await asyncio.gather(
                loop.run_in_executor(process_pool, process_inner),
                loop.run_in_executor(process_pool, process_inner),
                loop.run_in_executor(process_pool, process_inner),
                loop.run_in_executor(process_pool, process_inner),
            )
        )

    loop.run_until_complete(main())
