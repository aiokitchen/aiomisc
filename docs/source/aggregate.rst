``@aiomisc.aggregate``
======================

Parametric decorator that aggregates multiple
(but no more than ``max_count`` defaulting to ``None``) single-argument
executions (``res1 = await func(arg1)``, ``res2 = await func(arg2)``, ...)
of an asynchronous function with variadic positional arguments
(``async def func(*args, pho=1, bo=2) -> Iterable``) into its single execution
with multiple positional arguments
(``res1, res2, ... = await func(arg1, arg2, ...)``) collected within a time
window ``leeway_ms``. It offers a trade-off between latency and throughput.

If ``func`` raises an exception, then, all of the aggregated calls will
propagate the same exception. If one of the aggregated calls gets canceled
during the ``func`` execution, then, another will try to execute the ``func``.

This decorator may be useful if the ``func`` executes slow IO-tasks,
is frequently called, and using cache is not a good option. As a toy example,
assume that ``func`` fetches a record from the database by user ID and it is
called during each request to our service. If it takes 100 ms to fetch a
record and the load is 1000 RPS, then, with a 10% increase of the delay
(to 110 ms), it may decrease the number of requests to the database by
10 times (to 100 QPS).

.. image:: /_static/aggregate-flow.svg

.. code-block:: python
    :name: test_aggregate

    import asyncio
    import math
    from aiomisc import aggregate, entrypoint

    @aggregate(leeway_ms=10, max_count=2)
    async def pow(*nums: float, power: float = 2.0):
        return [math.pow(num, power) for num in nums]

    async def main():
        await asyncio.gather(pow(1.0), pow(2.0))

    with entrypoint() as loop:
        loop.run_until_complete(main())

To employ a more low-level approach one can use `aggregate_async` instead.
In this case, the aggregating function accepts `Arg` parameters, each containing
`value` and `future` attributes. It is responsible for setting the results
of execution for all the futures (instead of returning values).

.. code-block:: python
    :name: test_aggregate_async

    import asyncio
    import math
    from aiomisc import aggregate_async, entrypoint
    from aiomisc.aggregate import Arg


    @aggregate_async(leeway_ms=10, max_count=2)
    async def pow(*args: Arg, power: float = 2.0):
        for arg in args:
            arg.future.set_result(math.pow(arg.value, power))

    async def main():
        await asyncio.gather(pow(1), pow(2))

    with entrypoint() as loop:
        loop.run_until_complete(main())
