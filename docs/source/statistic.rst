Statistic counters
==================

``aiomisc`` contains internal statistic counters. You may read this by
`aiomisc.get_statistics()` function.

Statistic instances create dynamically. You might set custom names for this
using ``statistic_name: Optional[str] = None`` argument for compatible
entities.

.. code-block:: python

    import aiomisc

    async def main():
        for metric in aiomisc.get_statistics():
            print(
                str(metric.kind.__name__),
                metric.name,
                metric.metric,
                metric.value
            )


    with aiomisc.entrypoint() as loop:
        loop.run_until_complete(main())


This code will print something like this:

.. code-block::

    ContextStatistic None get 0
    ContextStatistic None set 0
    ThreadPoolStatistic logger submitted 1
    ThreadPoolStatistic logger sum_time 0
    ThreadPoolStatistic logger threads 1
    ThreadPoolStatistic logger done 0
    ThreadPoolStatistic logger success 0
    ThreadPoolStatistic logger error 0
    ThreadPoolStatistic default submitted 0
    ThreadPoolStatistic default sum_time 0
    ThreadPoolStatistic default threads 12
    ThreadPoolStatistic default done 0
    ThreadPoolStatistic default success 0
    ThreadPoolStatistic default error 0
