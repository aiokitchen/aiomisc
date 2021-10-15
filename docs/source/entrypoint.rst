entrypoint
==========

In the generic case, the entrypoint helper creates an event loop and cancels already
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
        log_format='color',                         # default when "rich" absent
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

Configuration from environment
++++++++++++++++++++++++++++++

Module support configuration from environment variables:

* `AIOMISC_LOG_LEVEL` - default logging level
* `AIOMISC_LOG_FORMAT` - default log format
* `AIOMISC_LOG_CONFIG` - should logging be configured
* `AIOMISC_LOG_FLUSH` - interval between logs flushing from buffer
* `AIOMISC_LOG_BUFFERING` - should logging be buffered
* `AIOMISC_LOG_BUFFER_SIZE` - maximum log buffer size
* `AIOMISC_POOL_SIZE` - thread pool size


``run()`` shortcut
==================

``aiomisc.run()`` - it's the short way to create and destroy
``aiomisc.entrypoint``. It's very similar to ``asyncio.run()``
but handle ``Service``'s and other ``entrypoint``'s kwargs.

.. code-block:: python
    :name: test_ep_run_simple

    import asyncio
    import aiomisc

    async def main():
        loop = asyncio.get_event_loop()
        now = loop.time()
        await asyncio.sleep(0.1)
        assert now < loop.time()


    aiomisc.run(main())
