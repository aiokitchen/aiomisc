Async backoff
=============

Abstraction:

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
