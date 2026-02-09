``@aiomisc.timeout``
====================

Decorator that ensures the execution time limit for the decorated
function is met.

.. code-block:: python

    from aiomisc import timeout

    @timeout(1)
    async def bad_func():
        await asyncio.sleep(2)


What happens on timeout
+++++++++++++++++++++++

When the decorated function exceeds the specified time limit,
an ``asyncio.TimeoutError`` exception is raised. The underlying
coroutine is cancelled automatically.

.. code-block:: python

    import asyncio
    from aiomisc import timeout

    @timeout(1)
    async def slow_operation():
        await asyncio.sleep(10)
        return "completed"

    async def main():
        try:
            result = await slow_operation()
        except asyncio.TimeoutError:
            print("Operation timed out!")

    asyncio.run(main())


Handling TimeoutError
+++++++++++++++++++++

You should always handle ``asyncio.TimeoutError`` when calling
functions decorated with ``@timeout``, especially in production code:

.. code-block:: python

    import asyncio
    from aiomisc import timeout

    @timeout(5)
    async def fetch_data():
        # Simulate network request
        await asyncio.sleep(10)
        return {"data": "value"}

    async def main():
        try:
            data = await fetch_data()
            print(f"Got data: {data}")
        except asyncio.TimeoutError:
            print("Request timed out, using default value")
            data = {"data": "default"}

    asyncio.run(main())


Comparison with asyncio.wait_for
++++++++++++++++++++++++++++++++

The ``@timeout`` decorator provides similar functionality to
``asyncio.wait_for``, but with a cleaner decorator-based syntax:

+-----------------------------------+-----------------------------------+
| asyncio.wait_for                  | @aiomisc.timeout                  |
+===================================+===================================+
| .. code-block:: python            | .. code-block:: python            |
|                                   |                                   |
|     async def fetch():            |     @timeout(5)                   |
|         await asyncio.sleep(10)   |     async def fetch():            |
|                                   |         await asyncio.sleep(10)   |
|     # At call site:               |                                   |
|     await asyncio.wait_for(       |     # At call site:               |
|         fetch(), timeout=5        |     await fetch()                 |
|     )                             |                                   |
+-----------------------------------+-----------------------------------+

The decorator approach is useful when:

* You want to enforce a timeout for all calls to a function
* The timeout is a property of the function itself, not the caller
* You want cleaner call-site code


Examples with different values
++++++++++++++++++++++++++++++

The timeout value is specified in seconds and can be an integer or float:

.. code-block:: python

    from aiomisc import timeout

    # 100 milliseconds timeout
    @timeout(0.1)
    async def quick_check():
        await asyncio.sleep(0.05)
        return True

    # 30 seconds timeout for long operations
    @timeout(30)
    async def long_operation():
        await asyncio.sleep(25)
        return "done"

    # 2.5 seconds timeout
    @timeout(2.5)
    async def medium_operation():
        await asyncio.sleep(2)
        return "completed"
