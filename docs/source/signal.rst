Signal
======

You can register async callback functions for specific events of an entrypoint.

pre_start
+++++++++

``pre_start`` signal occurs on entrypoint start up before any service have started.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.PRE_START)
    async def prepare_database(entrypoint, services):
      ...

    with entrypoint() as loop:
        loop.run_forever()


post_stop
+++++++++

``post_stop`` signal occurs on entrypoint shutdown after all services have been
stopped.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.POST_STOP)
    async def cleanup(entrypoint):
      ...

    with entrypoint() as loop:
        loop.run_forever()
