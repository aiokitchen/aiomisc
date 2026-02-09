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

During graceful shutdown method ``stop()`` will be called first,
and after that, all running tasks will be canceled (including ``start()``).


This package contains some useful base classes for simple services writing.

.. toctree::
   :maxdepth: 2

   network
   periodic
   configuration
   web
   grpc
   system
