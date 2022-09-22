aiomisc - miscellaneous utils for asyncio
=========================================

.. image:: https://coveralls.io/repos/github/aiokitchen/aiomisc/badge.svg?branch=master
   :target: https://coveralls.io/github/aiokitchen/aiomisc
   :alt: Coveralls

.. image:: https://github.com/aiokitchen/aiomisc/workflows/tox/badge.svg
   :target: https://github.com/aiokitchen/aiomisc/actions?query=workflow%3Atox
   :alt: Actions

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

Installing from PyPI:

.. code-block:: bash

    pip3 install aiomisc

With uvloop_:

.. code-block:: bash

    pip3 install "aiomisc[uvloop]"


With aiohttp_:

.. code-block:: bash

    pip3 install "aiomisc[aiohttp]"


Installing from github.com:

.. code-block:: bash

    pip3 install git+https://github.com/aiokitchen/aiomisc.git
    pip3 install \
        https://github.com/aiokitchen/aiomisc/archive/refs/heads/master.zip

.. _uvloop: https://pypi.org/project/uvloop
.. _aiohttp: https://pypi.org/project/aiohttp


Quick Start
-----------

Complete the :doc:`/tutorial` or see this quick start.

Async entrypoint with logging and useful arguments:

.. code-block:: python

    import asyncio
    import logging

    import aiomisc

    log = logging.getLogger(__name__)

    async def main():
        log.info('Starting')
        await asyncio.sleep(3)
        log.info('Exiting')


    if __name__ == '__main__':
        with entrypoint(
            log_level="info", log_format="color"
        ) as loop:
            loop.run_until_complete(main())


Install event loop on program start:

.. code-block:: python
    :name: test_index_get_loop

    import asyncio
    import aiomisc

    # Installing uvloop event loop
    # and set `aiomisc.thread_pool.ThreadPoolExecutor`
    # as default executor
    aiomisc.new_event_loop()

    async def main():
        await asyncio.sleep(1)

    if __name__ == '__main__':
        loop = asyncio.get_event_loop()
        loop.run_until_complete(main())


Close current event loop and install a new one:

.. code-block:: python
    :name: test_index_new_loop

    import asyncio
    import aiomisc

    async def main():
        await asyncio.sleep(3)

    if __name__ == '__main__':
        loop = aiomisc.new_event_loop()
        loop.run_until_complete(main())

Versioning
----------

This software follows `Semantic Versioning`_


How to develop?
---------------

Should be installed:

* `virtualenv`
* GNU Make as `make`
* Python 3.7+ as `python3`


For setting up developer environment just type

    .. code-block::

        make develop


.. _Semantic Versioning: http://semver.org/

Table Of Contents
+++++++++++++++++

.. toctree::
   :glob:
   :numbered:
   :maxdepth: 3

   tutorial
   modules
   api/index
