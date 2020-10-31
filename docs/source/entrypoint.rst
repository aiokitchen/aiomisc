entrypoint
==========

In generic case the entrypoint helper creates event loop and cancels already
running coroutines on exit.

.. code-block:: python

    import asyncio
    import aiomisc

    async def main():
        await asyncio.sleep(1)

    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


Complete example:

.. code-block:: python

    import asyncio
    import aiomisc
    import logging

    async def main():
        while True:
            await asyncio.sleep(1)
            logging.info("Hello there")

    with aiomisc.entrypoint(
        pool_size=2,
        log_level='info',
        log_format='color',                         # default
        log_buffer_size=1024,                       # default
        log_flush_interval=0.2,                     # default
        log_config=True,                            # default
        policy=asyncio.DefaultEventLoopPolicy(),    # default
        debug=False,                                # default
    ) as loop:
        loop.create_task(main())
        loop.run_forever()

Running entrypoint from async code

.. code-block:: python

    import asyncio
    import aiomisc

    class MyPeriodicService(PeriodicService):
        async def callback(self):
            log.info('Running periodic callback')
            # ...

    async def main():
        service = MyPeriodicService(interval=60, delay=0)  # once per minute

        # returns an entrypoint instance because event-loop
        # already running and might be get via asyncio.get_event_loop()
        async with aiomisc.entrypoint(service) as ep:
            await ep.closing()


    asyncio.run(main())
