Plugins
=======

aiomisc can be extended with plugins as separate packages. Plugins can
enhance aiomisc by mean of signals_.

.. _signals: #signal

In order to make your plugin discoverable by aiomisc you should add
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


Modules which provided in ``entry_points`` should have ``setup`` function.
This functions would be called by aiomisc and must contain signals connecting.

.. code-block:: python

    async def hello(entrypoint, services):
        print('Hello from aiomisc plugin')


    def setup():
        from aiomisc import entrypoint

        entrypoint.PRE_START.connect(hello)
