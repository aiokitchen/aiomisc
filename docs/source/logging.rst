Logging configuration
=====================

Default logging configuration might be configured by setting environment variables:

* `AIOMISC_LOG_LEVEL` - default logging level
* `AIOMISC_LOG_FORMAT` - default log format
* `AIOMISC_LOG_CONFIG` - should logging be configured
* `AIOMISC_LOG_FLUSH` - interval between logs flushing from buffer
* `AIOMISC_LOG_BUFFER` - maximum log buffer size

.. code-block:: shell

    $ export AIOMISC_LOG_LEVEL=debug
    $ export AIOMISC_LOG_FORMAT=rich


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

JournalD
++++++++

`JournalD`_ daemon for collecting logs. It's a part of the systemd.
`aiomisc.basic_config` has support for using `JournalD`_ for store logs.

.. note::

    This handler is the default when the program starting as a systemd service.

    `aiomisc.log.LogFormat.default()` will returns `journald`  in this case.

.. code-block:: python

    import logging
    from aiomisc.log import basic_config

    # Configure rich log handler
    basic_config(level=logging.INFO, buffered=False, log_format='journald')

    logging.info("JournalD log record")

.. _JournalD: https://www.freedesktop.org/software/systemd/man/systemd-journald.service.html


Rich
++++

`Rich`_ is a Python library for rich text and beautiful formatting in the terminal.

`aiomisc.basic_config` has support for using `Rich`_ as a logging handler.
But it isn't dependency and you have to install `Rich`_ manually.

.. code-block:: bash

    pip install rich

.. note::

    This handler is the default when the `Rich` has been installed.

.. code-block:: python
    :name: test_rich_handlers

    import logging
    from aiomisc.log import basic_config

    # Configure rich log handler
    basic_config(level=logging.INFO, buffered=False, log_format='rich')

    logging.info("Rich logger")

    # Configure rich log handler with rich tracebacks display
    basic_config(level=logging.INFO, buffered=False, log_format='rich_tb')

    try:
        1 / 0
    except:
        logging.exception("Rich traceback logger")

.. _Rich: https://pypi.org/project/rich/

Disabled
++++++++

Disable to configure logging handler. Useful when you want to configure your own logging handlers using
`handlers=` argument.

.. code-block:: python
    :name: test_log_disabled

    import logging
    from aiomisc.log import basic_config

    # Configure your own log handlers
    basic_config(
        level=logging.INFO,
        log_format='disabled',
        handlers=[logging.StreamHandler()],
        buffered=False,
    )

    logging.info("Use default python logger for example")



Buffered log handler
++++++++++++++++++++

Parameter `buffered=True` enables a memory buffer that flushes logs in a thread. In case the `handlers=`
each will be buffered.

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
