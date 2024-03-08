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
            "aiomisc": ["myplugin = aiomisc_myplugin.plugin"]
        },
        # ...
    )

If you use `pyproject.toml` you might define it like this:

.. code-block:: ini

    [tool.poetry.plugins.aiomisc]
    myplugin = "aiomisc_myplugin.plugin"


Modules provided in ``entry_points`` should have ``setup`` function.
These functions would be called by aiomisc and must contain signals connecting.

If the services are started dynamically, the attached functions will run every
time the services are started and stopped, however, only services that are
currently starting or stopping will be in the ``services`` parameter.

.. code-block:: python
    :name: test_plugin

    # Content of: ``aiomisc_myplugin/plugin.py``
    from typing import Tuple
    from threading import Event

    import aiomisc


    event = Event()
    # Will be shown in ``python -m aiomisc.plugins``
    __doc__ = "Example plugin"


    async def hello(
        *,
        entrypoint: aiomisc.Entrypoint,
        services: Tuple[aiomisc.Service, ...]
    ) -> None:
        print('Hello from aiomisc plugin')
        event.set()


    def setup() -> None:
        """
        This code will be called by loading plugins declared in
        ``pyproject.toml`` or ``setup.py``.
        """
        aiomisc.Entrypoint.PRE_START.connect(hello)

    # Content of: ``my_plugin_example.py``
    # ======================================================================
    # The code below is not related to the plugin, but serves to demonstrate
    # how it works.
    # ======================================================================
    def main():
        """ some function in user code """

        # This function will be called by aiomisc.plugin module
        # in this example it's just for demonstration.
        setup()

        assert not event.is_set()

        with aiomisc.entrypoint() as loop:
            pass

        assert event.is_set()

    main()

    # remove the plugin on when unneeded
    aiomisc.entrypoint.PRE_START.disconnect(hello)


The following signals are available in total:

* ``Entrypoint.PRE_START`` - Will be called before `starting` services.
* ``Entrypoint.PRE_STOP`` - Will be called before `stopping` services.
* ``Entrypoint.POST_START`` - Will be called after services has been `started`.
* ``Entrypoint.POST_STOP`` - Will be called after services has been `stopped`.


List available plugins
----------------------

To see a list of all available plugins, you can call from the
command line ``python -m aiomisc.plugins``:

.. code-block::

    $ python -m aiomisc.plugins
    [11:14:42] INFO     Available 1 plugins.
               INFO     'systemd_watchdog' - Adds SystemD watchdog support to the entrypoint.
    systemd_watchdog

You can also change the behavior and output of the list of modules.
To do this, there are the following flags:

.. code-block::

    $ python3 -m aiomisc.plugins -h
    usage: python3 -m aiomisc.plugins [-h] [-q] [-n]
                                      [-l {critical,error,warning,info,debug,notset}]
                                      [-F {stream,color,json,syslog,plain,journald,rich,rich_tb}]

    optional arguments:
      -h, --help            show this help message and exit
      -q, -s, --quiet, --silent
                            Disable logs and just output plugin-list, alias for
                            --log-level=critical
      -n, --no-output       Disable output plugin-list to the stdout
      -l {critical,error,warning,info,debug,notset}, --log-level {critical,error,warning,info,debug,notset}
                            Logging level
      -F {stream,color,json,syslog,plain,journald,rich,rich_tb}, --log-format {stream,color,json,syslog,plain,journald,rich,rich_tb}
                            Logging format

Here are some run examples.

.. code-block::

    $ python3 -m aiomisc.plugins -n
    [12:25:57] INFO     Available 1 plugins.
               INFO     'systemd_watchdog' - Adds SystemD watchdog support to the entrypoint.

This prints human-readable list of plugins and its descriptions.


.. code-block::

    $ python3 -m aiomisc.plugins -s
    systemd_watchdog

This useful for ``grep`` or other pipelining tools.

The default prints both, the human-readable log to stderr and the list
of plugins to stdout, so you can use this without options in a pipeline,
and read the list to stderr.
