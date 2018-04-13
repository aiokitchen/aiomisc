aiomisc - miscellaneous utils for asyncio
=========================================

.. image:: https://coveralls.io/repos/github/mosquito/aiomisc/badge.svg?branch=master
    :target: https://coveralls.io/github/mosquito/aiomisc
    :alt: Coveralls

.. image:: https://travis-ci.org/mosquito/aiomisc.svg
    :target: https://travis-ci.org/mosquito/aiomisc
    :alt: Travis CI

.. image:: https://img.shields.io/pypi/v/aiomisc.svg
    :target: https://pypi.python.org/pypi/aiomisc/
    :alt: Latest Version

.. image:: https://img.shields.io/pypi/wheel/aiomisc.svg
    :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/pyversions/aiomisc.svg
    :target: https://pypi.python.org/pypi/aiomisc/

.. image:: https://img.shields.io/pypi/l/aiomisc.svg
    :target: https://pypi.python.org/pypi/aiomisc/

Miscellaneous utils for asyncio.


Installation
------------

Installing from pypi:

.. code-block:: bash

    pip3 install aiomisc


Installing from github.com:

.. code-block:: bash

    pip3 install git+https://github.com/mosquito/aiomisc.git


Quick Start
-----------

Install event loop on the program starts.

.. code-block:: python

    import asyncio
    from aiomisc.utils import new_event_loop


    # Installing uvloop event loop
    # and set `aiomisc.thread_pool.ThreadPoolExecutor`
    # as default executor
    new_event_loop()


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())


Close current event loop and install the new one:

.. code-block:: python

    import asyncio
    from aiomisc.utils import new_event_loop


    async def main():
        await asyncio.sleep(3)


    if __name__ == '__main__':
        loop = new_event_loop()
        loop.run_until_complete(main())


threaded decorator
------------------

Wraps blocking function and run it on the thread pool.


.. code-block:: python

    import asyncio
    import time
    from aiomisc.utils import new_event_loop
    from aiomisc.thread_pool import threaded


    @threaded
    def blocking_function():
        time.sleep(1)


    async def main():
        # Running in parallel
        await asyncio.gather(
            blocking_function(),
            blocking_function(),
        )


    if __name__ == '__main__':
        loop = new_event_loop()
        loop.run_until_complete(main())


Fast ThreadPoolExecutor
-----------------------

This is the simple thread pool implementation.

Installation as a default thread pool:

.. code-block:: python

    import asyncio
    from aiomisc.thread_pool import ThreadPoolExecutor

    loop = asyncio.get_event_loop()
    thread_pool = ThreadPoolExecutor(4, loop=loop)
    loop.set_default_executor(thread_pool)


Bind socket
-----------

.. code-block:: python

    from aiomisc.utils import bind_socket

    # IPv4 socket
    sock = bind_socket(address="127.0.0.1", port=1234)

    # IPv6 socket (on Linux IPv4 socket will be bind too)
    sock = bind_socket(address="::1", port=1234)


Periodic callback
-----------------

Runs coroutine function periodically

.. code-block:: python

    import asyncio
    import time
    from aiomisc.utils import new_event_loop
    from aiomisc.periodic import PeriodicCallback


    async def periodic_function():
        print("Hello")


    if __name__ == '__main__':
        loop = new_event_loop()

        periodic = PeriodicCallback(periodic_function)

        # Call it each second
        periodic.start(1)

        loop.run_forever()


Logging configuration
---------------------

Setting up colorized logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='color')

Setting up json logs:

.. code-block:: python

    import logging
    from aiomisc.log import basic_config


    # Configure logging
    basic_config(level=logging.INFO, buffered=False, log_format='json')


Buffered log handler
++++++++++++++++++++

Parameter `buffered=True` enables memory buffer which flushing logs in thread.

.. code-block:: python

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
            flush_interval=2
        )

        periodic = PeriodicCallback(write_log, loop)
        periodic.start(0.3)

        loop.run_forever()


How to develop?
---------------

Should be installed:

* `virtualenv`
* GNU Make as `make`
* Python 3.5+ as `python3`


For setting up developer environment just type::

    make develop


