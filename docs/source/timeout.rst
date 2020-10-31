timeout decorator
=================

Decorator that ensures the execution time limit for decorated function is met.

.. code-block:: python

    from aiomisc import timeout

    @timeout(1)
    async def bad_func():
        await asyncio.sleep(2)
