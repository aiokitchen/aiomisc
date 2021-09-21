Logging configuration
=====================

Color
+++++

Setting up colorized logs:

.. code-block:: python
    :name: test_logging_color

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='color')

JSON
++++

Setting up json logs:

.. code-block:: python
    :name: test_logging_json

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='json')


Buffered log handler
++++++++++++++++++++

Parameter `buffered=True` enables memory buffer that flushes logs in a thread.

.. code-block:: python
    :name: test_logging_buffered

    import asyncio
    import logging
    from aiomisc.log import basic_config
    from aiomisc.periodic import PeriodicCallback
    from aiomisc.utils import new_event_loop


    # Configure logging globally
    basic_config(level=logging.INFO, buffered=False, log_format='json')

    async def write_log(loop):
        logging.info("Hello %f", loop.time())

    if __name__ == '__main__':
        loop = new_event_loop()

        # Configure
        basic_config(
            level=logging.INFO,
            buffered=True,
            log_format='color',
            flush_interval=0.5
        )

        periodic = PeriodicCallback(write_log, loop)
        periodic.start(0.3)

        # Wait for flush just for example
        loop.run_until_complete(asyncio.sleep(1))


.. note::

    ``entrypoint`` accepts ``log_format`` parameter for configure it.

    List of all supported log formats is available from
    ``aiomisc.log.LogFormat.choices()``
