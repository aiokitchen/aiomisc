``Signal``
==========

You can register async callback functions for specific events of an entrypoint.

``pre_start``
+++++++++++++

``pre_start`` signal occurs on entrypoint starting up before any service has started.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.PRE_START)
    async def prepare_database(entrypoint, services):
      ...

    with entrypoint() as loop:
        loop.run_forever()


``post_start``
++++++++++++++

``post_start`` signal occurs next entrypoint starting up after all services have
been started.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.POST_START)
    async def startup_notifier(entrypoint, services):
      ...

    with entrypoint() as loop:
        loop.run_forever()


``pre_stop``
++++++++++++

``pre_stop`` signal occurs on entrypoint shutdown before any service have been
stopped.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.PRE_STOP)
    async def shutdown_notifier(entrypoint):
      ...

    with entrypoint() as loop:
        loop.run_forever()


``post_stop``
+++++++++++++

``post_stop`` signal occurs on entrypoint shutdown after all services have been
stopped.

.. code-block:: python

    from aiomisc import entrypoint, receiver

    @receiver(entrypoint.POST_STOP)
    async def cleanup(entrypoint):
      ...

    with entrypoint() as loop:
        loop.run_forever()
