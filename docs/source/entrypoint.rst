entrypoint
==========

In the generic case, the entrypoint helper creates an event loop and
cancels already running coroutines on exit.

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
    import signal

    async def main():
        await asyncio.sleep(1)
        logging.info("Hello there")

    with aiomisc.entrypoint(
        pool_size=2,
        log_level='info',
        log_format='color',                            # default when "rich" absent
        log_buffer_size=1024,                          # default
        log_flush_interval=0.2,                        # default
        log_config=True,                               # default
        policy=asyncio.DefaultEventLoopPolicy(),       # default
        debug=False,                                   # default
        catch_signals=(signal.SIGINT, signal.SIGTERM), # default
        shutdown_timeout=60,                           # default
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

Dynamic running of services
+++++++++++++++++++++++++++

Sometimes it is not enough to add services to the entrypoint at the start,
or it is not possible to get the service parameters before the start of
the event-loop. In this case it is possible to start services after the
event-loop has started, this feature available from version ``17``.

.. code-block:: python

    import asyncio
    import aiomisc
    import logging

    from aiomisc.service.periodic import PeriodicService

    log = logging.getLogger(__name__)


    class MyPeriodicService(PeriodicService):
        async def callback(self):
            log.info('Running periodic callback')


    async def add_services():
        entrypoint = aiomisc.entrypoint.get_current()

        services = [
            MyPeriodicService(interval=2, delay=1),
            MyPeriodicService(interval=2, delay=0),
        ]

        await entrypoint.start_services(*services)
        await asyncio.sleep(10)
        await entrypoint.stop_services(*services)


    with aiomisc.entrypoint() as loop:
        loop.create_task(add_services())
        loop.run_forever()


Configuration from environment
++++++++++++++++++++++++++++++

Module support configuration from environment variables:

* ``AIOMISC_LOG_LEVEL`` - default logging level
* ``AIOMISC_LOG_FORMAT`` - default log format
* ``AIOMISC_LOG_DATE_FORMAT`` - default logging date format
* ``AIOMISC_LOG_CONFIG`` - should logging be configured
* ``AIOMISC_LOG_FLUSH`` - interval between logs flushing from buffer
* ``AIOMISC_LOG_BUFFERING`` - should logging be buffered
* ``AIOMISC_LOG_BUFFER_SIZE`` - maximum log buffer size
* ``AIOMISC_POOL_SIZE`` - thread pool size
* ``AIOMISC_USE_UVLOOP`` - should use uvloop when it available, ``0`` to disable
* ``AIOMISC_SHUTDOWN_TIMEOUT`` - If, after receiving the signal, the program
  does not terminate within this timeout, a force-exit occurs.


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

Logging configuration
=====================

``entrypoint`` accepts ``log_format`` argument with a specific set of formats,
in which logs will be written to stderr:

* ``stream`` - Python's default logging handler
* ``color`` - logging with `colorlog` module
* ``json`` - json structure per each line
* ``syslog`` - logging using stdlib `logging.handlers.SysLogHandler`
* ``plain`` - just log messages, without date or level info
* ``journald`` - available only when `logging-journald` module
  has been installed.
* ``rich``/``rich_tb`` - available only when `rich` module has been installed.
  ``rich_tb`` it's the same as ``rich`` but with fully expanded tracebacks.

Additionally, you can specify log level using ``log_level`` argument and date
format using ``log_date_format`` parameters.

An ``entrypoint`` will call ``aiomisc.log.basic_config`` function implicitly
using passed ``log_*`` parameters. Alternatively you can call
``aiomisc.log.basic_config`` function manually passing it already created
eventloop.

However, you can configure logging earlier using ``aiomisc_log.basic_config``,
but you will lose log buffering and flushing in a separate thread.
This function is what is actually called during the logging configuration,
the ``entrypoint`` passes a wrapper for the handler there to flush it into
the separate thread.

.. code-block:: python

    import logging

    from aiomisc_log import basic_config


    basic_config(log_format="color")
    logging.info("Hello")

If you want to configure logging before the ``entrypoint`` is started,
for example after the arguments parsing, it is safe to configure it twice
(or more).

.. code-block:: python

    import logging

    import aiomisc
    from aiomisc_log import basic_config


    basic_config(log_format="color")
    logging.info("Hello from usual python")


    async def main():
        logging.info("Hello from async python")


    with aiomisc.entrypoint(log_format="color") as loop:
        loop.run_until_complete(main())


Sometimes you want to configure logging manually, the following example
demonstrates how to do this:

.. code-block:: python

    import os
    import logging
    from logging.handlers import RotatingFileHandler
    from gzip import GzipFile

    import aiomisc


    class GzipLogFile(GzipFile):
        def write(self, data) -> int:
            if isinstance(data, str):
                data = data.encode()
            return super().write(data)


    class RotatingGzipFileHandler(RotatingFileHandler):
        """ Really added just for example you have to test it properly """

        def shouldRollover(self, record):
            if not os.path.isfile(self.baseFilename):
                return False
            if self.stream is None:
                self.stream = self._open()
            return 0 < self.maxBytes < os.stat(self.baseFilename).st_size

        def _open(self):
            return GzipLogFile(filename=self.baseFilename, mode=self.mode)


    async def main():
        for _ in range(1_000):
            logging.info("Hello world")


    with aiomisc.entrypoint(log_config=False) as loop:
        gzip_handler = RotatingGzipFileHandler(
            "app.log.gz",
            # Maximum 100 files by 10 megabytes
            maxBytes=10 * 2 ** 20, backupCount=100
        )
        stream_handler = logging.StreamHandler()

        formatter = logging.Formatter(
            "[%(asctime)s] <%(levelname)s> "
            "%(filename)s:%(lineno)d (%(threadName)s): %(message)s"
        )

        gzip_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        logging.basicConfig(
            level=logging.INFO,
            # Wrapping all handlers in separate streams will not block the
            # event-loop even if gzip takes a long time to open the
            # file.
            handlers=map(
                aiomisc.log.wrap_logging_handler,
                (gzip_handler, stream_handler)
            )
        )
        loop.run_until_complete(main())
