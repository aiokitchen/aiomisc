entrypoint
==========

In generic case the entrypoint helper creates event loop and cancels already
running coroutines on exit.

.. code-block:: python
    :name: test_entrypoint_simple

    import asyncio
    import aiomisc

    async def main():
        await asyncio.sleep(1)

    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


Complete example:

.. code-block:: python
    :name: test_entrypoint_complex

    import asyncio
    import aiomisc
    import logging

    async def main():
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
        loop.run_until_complete(main())

Running entrypoint from async code

.. code-block:: python
    :name: test_entrypoint_async

    import asyncio
    import aiomisc
    import logging
    from aiomisc.service.periodic import PeriodicService

    log = logging.getLogger(__name__)

    class MyPeriodicService(PeriodicService):
        async def callback(self):
            log.info('Running periodic callback')
            # ...

    async def main():
        service = MyPeriodicService(interval=1, delay=0)  # once per minute

        # returns an entrypoint instance because event-loop
        # already running and might be get via asyncio.get_event_loop()
        async with aiomisc.entrypoint(service) as ep:
            try:
                await asyncio.wait_for(ep.closing(), timeout=1)
            except asyncio.TimeoutError:
                pass


    asyncio.run(main())
