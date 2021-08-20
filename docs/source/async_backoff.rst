Async backoff
=============

``asyncbackoff`` it's a decorator that helps you guarantee maximal async
function execution and retrying policy.

The main principle might be described in five rules:

* function will be cancelled when executed longer than
  ``deadline`` (if specified)
* function will be cancelled when executed longer than
  ``attempt_timeout`` (if specified) and will be retried
* Reattempts performs after ``pause`` seconds (if specified, default is ``0``)
* Reattempts will be performed not more than ``max_tries`` times.
* ``giveup`` argument is a function that decides should give
  up the reattempts or continue retrying.

All these rules work at the same time.

Arguments description:

* ``attempt_timeout`` is maximum execution time for one execution attempt.
* ``deadline`` is maximum execution time for all execution attempts.
* ``pause`` is time gap between execution attempts.
* ``exceptions`` retrying when this exceptions was raised.
* ``giveup`` (keyword only) is a predicate function which can decide by a given
  exception if we should continue to do retries.
* ``max_tries`` (keyword only) is maximum count of execution attempts (>= 1).

Decorator that ensures that ``attempt_timeout`` and ``deadline`` time
limits are met by decorated function.

In case of exception function will be called again with similar arguments after
``pause`` seconds.


Position arguments notation:

.. code-block:: python

    from aiomisc import asyncbackoff

    attempt_timeout = 0.1
    deadline = 1
    pause = 0.1

    @asyncbackoff(attempt_timeout, deadline, pause)
    async def db_fetch():
        ...


    @asyncbackoff(0.1, 1, 0.1)
    async def db_save(data: dict):
        ...


    # Passing exceptions for handling
    @asyncbackoff(0.1, 1, 0.1, TypeError, RuntimeError, ValueError)
    async def db_fetch(data: dict):
        ...


Keyword arguments notation:

.. code-block:: python

    from aiomisc import asyncbackoff

    attempt_timeout = 0.1
    deadline = 1
    pause = 0.1

    @asyncbackoff(attempt_timeout=attempt_timeout,
                  deadline=deadline, pause=pause)
    async def db_fetch():
        ...


    @asyncbackoff(attempt_timeout=0.1, deadline=1, pause=0.1)
    async def db_save(data: dict):
        ...


    # Passing exceptions for handling
    @asyncbackoff(attempt_timeout=0.1, deadline=1, pause=0.1,
                  exceptions=[TypeError, RuntimeError, ValueError])
    async def db_fetch(data: dict):
        ...


    # Will be retried no more than 2 times (3 tries total)
    @asyncbackoff(attempt_timeout=0.5, deadline=1, pause=0.1, max_tries=3,
                  exceptions=[TypeError, RuntimeError, ValueError])
    async def db_fetch(data: dict):
        ...


    # Will be retried only on connection abort (on POSIX systems)
    @asyncbackoff(attempt_timeout=0.5, deadline=1, pause=0.1,
                  exceptions=[OSError],
                  giveup=lambda e: e.errno != errno.ECONNABORTED)
    async def db_fetch(data: dict):
        ...


asyncretry
==========

Shortcut of ``asyncbackoff(None, None, 0, *args, **kwargs)``. Just retries
``max_tries`` times.

.. note::

    By default will be retry when any Exception. It's very simple and useful
    in generic cases, but you should specify an exception list when your wrapped
    functions calling hundreds of times per second, cause you have a risk be
    the reason of denial of service in case your function calls remote service.

.. code-block:: python

    from aiomisc import asyncretry

    @asyncretry(5)
    async def try_download_file(url):
        ...

    @asyncretry(3, exceptions=(ConnectionError,))
    async def get_cluster_lock():
        ...
