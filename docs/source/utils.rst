Utilities
=========

``select``
++++++++++

In some cases, you should wait for only one of multiple tasks. ``select``
waits first passed awaitable object and returns the list of results.

.. code-block:: python

    import asyncio
    import aiomisc


    async def main():
        loop = asyncio.get_event_loop()
        event = asyncio.Event()
        future = asyncio.Future()

        loop.call_soon(event.set)

        await aiomisc.select(event.wait(), future)
        print(event.is_set())       # True

        event = asyncio.Event()
        future = asyncio.Future()

        loop.call_soon(future.set_result, True)

        results = await aiomisc.select(future, event.wait())
        future_result, event_result = results

        print(results.result())             # True
        print(results.result_idx)           # 0
        print(event_result, future_result)  # None, True


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


.. warning::

    When you don't want to cancel pending tasks pass ``cancel=False`` argument.
    In this case, you have to handle task completion manually or get warnings.


``cancel_tasks``
++++++++++++++++

All passed tasks will be canceled and the task will be returned:

.. code-block:: python

    import asyncio
    from aiomisc import cancel_tasks


    async def main():
        done, pending = await asyncio.wait([
            asyncio.sleep(i) for i in range(10)
        ], timeout=5)

        print("Done", len(done), "tasks")
        print("Pending", len(pending), "tasks")
        await cancel_tasks(pending)


    asyncio.run(main())


``awaitable``
+++++++++++++

Decorator wraps function and returns a function that returns awaitable object.
In case a function returns a future, the original future will be returned.
In case then the function returns a coroutine, the original coroutine will
be returned. In case than function returns a non-awaitable object, it's will
be wrapped to a new coroutine that just returns this object. It's useful
when you don't want to check function results before
use it in ``await`` expression.

.. code-block:: python

    import asyncio
    import aiomisc


    async def do_callback(func, *args):
        awaitable_func = aiomisc.awaitable(func)

        return await awaitable_func(*args)


    print(asyncio.run(do_callback(asyncio.sleep, 2)))
    print(asyncio.run(do_callback(lambda: 45)))

``bind_socket``
+++++++++++++++

Bind socket and set ``setblocking(False)`` for just created socket.
This detects ``address`` format and selects the socket family automatically.

.. code-block:: python

    from aiomisc import bind_socket

    # IPv4 socket
    sock = bind_socket(address="127.0.0.1", port=1234)

    # IPv6 socket (on Linux IPv4 socket will be bind too)
    sock = bind_socket(address="::1", port=1234)


``RecurringCallback``
+++++++++++++++++++++

Runs coroutine function periodically with user-defined strategy.

.. code-block:: python

    from typing import Union
    from aiomisc import new_event_loop, RecurringCallback


    async def callback():
        print("Hello")


    FIRST_CALL = False


    async def strategy(_: RecurringCallback) -> Union[int, float]:
        global FIRST_CALL
        if not FIRST_CALL:
            FIRST_CALL = True
            # Delay 5 second if just started
            return 5

        # Delay 10 seconds if it is not a first call
        return 10


    if __name__ == '__main__':
        loop = new_event_loop()

        periodic = RecurringCallback(callback)

        task = periodic.start(strategy)
        loop.run_forever()


The main purpose is this class is to provide ability to specify the
asynchronous strategy function, which can be written very flexible.

Also, with the special exceptions, you can control the behavior of the started
``RecurringCallback``.

.. code-block:: python

    from aiomisc import (
        new_event_loop, RecurringCallback, StrategySkip, StrategyStop
    )


    async def strategy(_: RecurringCallback) -> Union[int, float]:
        ...

        # Skip this attempt and wait 10 seconds
        raise StrategySkip(10)

        ...

        # Stop execution
        raise StrategyStop()

if the strategy function returns an incorrect value (not a number), or does
not raise special exceptions, the recurring execution is terminated.


``PeriodicCallback``
++++++++++++++++++++

Runs coroutine function periodically with an optional delay of the first
execution. Uses ``RecurringCallback`` under the hood.

.. code-block:: python

    import asyncio
    import time
    from aiomisc import new_event_loop, PeriodicCallback


    async def periodic_function():
        print("Hello")


    if __name__ == '__main__':
        loop = new_event_loop()

        periodic = PeriodicCallback(periodic_function)

        # Wait 10 seconds and call it each second after that
        periodic.start(1, delay=10)

        loop.run_forever()


``CronCallback``
++++++++++++++++

.. warning::

    You have to install ``croniter`` package for use this feature:

    .. code-block:: shell

        pip install croniter

    Or add extras when installing aiomisc:

    .. code-block:: shell

        pip install aiomisc[cron]



Runs coroutine function with cron scheduling execution.
Uses ``RecurringCallback`` under the hood.

.. code-block:: python

    import asyncio
    import time
    from aiomisc import new_event_loop, CronCallback


    async def cron_function():
        print("Hello")


    if __name__ == '__main__':
        loop = new_event_loop()

        periodic = CronCallback(cron_function)

        # call it each second after that
        periodic.start(spec="* * * * * *")

        loop.run_forever()
