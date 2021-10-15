Plugins
=======

aiomisc can be extended with plugins as separate packages. Plugins can
enhance aiomisc by mean of signals_.

.. _signals: #signal

To make your plugin discoverable by aiomisc you should add
``aiomisc.plugins`` entry to entry to ``entry_points`` argument of ``setup``
call in ``setup.py`` of a plugin.

.. code-block:: python

    # setup.py

    setup(
        # ...
        entry_points={
            "aiomisc.plugins": ["myplugin = aiomisc_myplugin.plugin"]
        },
        # ...
    )


Modules provided in ``entry_points`` should have ``setup`` function.
These functions would be called by aiomisc and must contain signals connecting.

.. code-block:: python
    :name: test_plugin

    from aiomisc import entrypoint
    from threading import Event


    event = Event()


    async def hello(entrypoint, services):
        print('Hello from aiomisc plugin')
        event.set()


    def setup():
        entrypoint.PRE_START.connect(hello)

    setup()

    assert not event.is_set()

    with entrypoint() as loop:
        pass

    assert event.is_set()
