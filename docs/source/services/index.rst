Services
========

``Services`` is an abstraction to help organize lots of different
tasks in one process. Each service must implement ``start()`` method and can
implement ``stop()`` method.

Service instance should be passed to the ``entrypoint``, and will be started
after the event loop has been created.

.. note::

   Current event-loop will be set before ``start()`` method called.
   The event loop will be set as current for this thread.

   Please avoid using ``asyncio.get_event_loop()`` explicitly inside
   ``start()`` method. Use ``self.loop`` instead:

   .. code-block:: python
      :name: test_service_start_event

      import asyncio
      from threading import Event
      from aiomisc import entrypoint, Service

      event = Event()

      class MyService(Service):
        async def start(self):
            # Send signal to entrypoint for continue running
            self.start_event.set()

            event.set()
            # Start service task
            await asyncio.sleep(3600)


      with entrypoint(MyService()) as loop:
          assert event.is_set()


Method ``start()`` creates as a separate task that can run forever. But in
this case ``self.start_event.set()`` should be called for notifying
``entrypoint``.

If one service fails during startup, pending starts from the same group and
their readiness waiters are cancelled and joined before the original error
is propagated. ``POST_START`` runs after this cleanup, including on failure.
Tasks unrelated to the entrypoint's startup group are left running.

During graceful shutdown, long-lived ``start()`` tasks are cancelled before
the services' ``stop()`` methods are called. Applications that need coordinated
draining or other work while service loops are active should quiesce that work
before exiting the entrypoint. When calling ``__aenter__()`` directly, call
``__aexit__()`` after a failed startup as well, to stop already-created services
and release their resources.


This package contains some useful base classes for simple services writing.

.. toctree::
   :maxdepth: 2

   network
   periodic
   configuration
   web
   grpc
   system
