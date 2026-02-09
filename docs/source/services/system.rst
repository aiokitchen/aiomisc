System Services
===============

This section covers system-level services for debugging, profiling,
monitoring, and process management.


.. _memory-tracer:

Memory Tracer
+++++++++++++

Simple and useful service for logging large python
objects allocated in memory.


.. code-block:: python

    import asyncio
    import os
    from aiomisc import entrypoint
    from aiomisc.service import MemoryTracer


    async def main():
        leaking = []

        while True:
            leaking.append(os.urandom(128))
            await asyncio.sleep(0)


    with entrypoint(MemoryTracer(interval=1, top_results=5)) as loop:
        loop.run_until_complete(main())


Output example:

.. code-block::

    [T:[1] Thread Pool] INFO:aiomisc.service.tracer: Top memory usage:
     Objects | Obj.Diff |   Memory | Mem.Diff | Traceback
          12 |       12 |   1.9KiB |   1.9KiB | aiomisc/periodic.py:40
          12 |       12 |   1.8KiB |   1.8KiB | aiomisc/entrypoint.py:93
           6 |        6 |   1.1KiB |   1.1KiB | aiomisc/thread_pool.py:71
           2 |        2 |   976.0B |   976.0B | aiomisc/thread_pool.py:44
           5 |        5 |   712.0B |   712.0B | aiomisc/thread_pool.py:52

    [T:[6] Thread Pool] INFO:aiomisc.service.tracer: Top memory usage:
     Objects | Obj.Diff |   Memory | Mem.Diff | Traceback
       43999 |    43999 |   7.1MiB |   7.1MiB | scratches/scratch_8.py:11
          47 |       47 |   4.7KiB |   4.7KiB | env/bin/../lib/python3.7/abc.py:143
          33 |       33 |   2.8KiB |   2.8KiB | 3.7/lib/python3.7/tracemalloc.py:113
          44 |       44 |   2.4KiB |   2.4KiB | 3.7/lib/python3.7/tracemalloc.py:185
          14 |       14 |   2.4KiB |   2.4KiB | aiomisc/periodic.py:40


.. _profiler:

Profiler
++++++++

Simple service for profiling.
Optional `path` argument can be provided to dump complete profiling data,
which can be later used by, for example, snakeviz.
Also can change ordering with the `order` argument ("cumulative" by default).


.. code-block:: python

    import asyncio
    import os
    from aiomisc import entrypoint
    from aiomisc.service import Profiler


    async def main():
        for i in range(100):
            time.sleep(0.01)


    with entrypoint(Profiler(interval=0.1, top_results=5)) as loop:
        loop.run_until_complete(main())


Output example:

.. code-block::

   108 function calls in 1.117 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
      100    1.117    0.011    1.117    0.011 {built-in method time.sleep}
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:89(__init__)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:99(init)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/pstats.py:118(load_stats)
        1    0.000    0.000    0.000    0.000 <...>/lib/python3.7/cProfile.py:50(create_stats)


.. _raven-service:

Raven service
+++++++++++++

Simple service for sending unhandled exceptions to the `sentry`_
service instance.

.. _sentry: https://sentry.io

Simple example:

.. code-block:: python

   import asyncio
   import logging
   import sys

   from aiomisc import entrypoint
   from aiomisc.version import __version__
   from aiomisc.service.raven import RavenSender


   async def main():
       while True:
           await asyncio.sleep(1)

           try:
               1 / 0
           except ZeroDivisionError:
               logging.exception("Exception")


   raven_sender = RavenSender(
       sentry_dsn=(
           "https://583ca3b555054f80873e751e8139e22a@o429974.ingest.sentry.io/"
           "5530251"
       ),
       client_options=dict(
           # Got environment variable SENTRY_NAME by default
           name="example-from-aiomisc",
           # Got environment variable SENTRY_ENVIRONMENT by default
           environment="simple_example",
           # Got environment variable SENTRY_RELEASE by default
           release=__version__,
       )
   )


   with entrypoint(raven_sender) as loop:
       loop.run_until_complete(main())

Full configuration:

.. code-block:: python

   import asyncio
   import logging
   import sys

   from aiomisc import entrypoint
   from aiomisc.version import __version__
   from aiomisc.service.raven import RavenSender


   async def main():
       while True:
           await asyncio.sleep(1)

           try:
               1 / 0
           except ZeroDivisionError:
               logging.exception("Exception")


   raven_sender = RavenSender(
       sentry_dsn=(
           "https://583ca3b555054f80873e751e8139e22a@o429974.ingest.sentry.io/"
           "5530251"
       ),
       client_options=dict(
           # Got environment variable SENTRY_NAME by default
           name="",
           # Got environment variable SENTRY_ENVIRONMENT by default
           environment="full_example",
           # Got environment variable SENTRY_RELEASE by default
           release=__version__,

           # Default options values
           include_paths=set(),
           exclude_paths=set(),
           auto_log_stacks=True,
           capture_locals=True,
           string_max_length=400,
           list_max_length=50,
           site=None,
           include_versions=True,
           processors=(
               'raven.processors.SanitizePasswordsProcessor',
           ),
           sanitize_keys=None,
           context={'sys.argv': getattr(sys, 'argv', [])[:]},
           tags={},
           sample_rate=1,
           ignore_exceptions=(),
       )
   )


   with entrypoint(raven_sender) as loop:
       loop.run_until_complete(main())

You will find the full specification of options in the `Raven documentation`_.

.. _Raven documentation: https://docs.sentry.io/clients/python/advanced/#client-arguments


``SDWatchdogService``
+++++++++++++++++++++

Ready to use service just adding to your entrypoint and notifying SystemD
service watchdog timer.

This can be safely added at any time, since if the service does not detect
systemd-related environment variables, then its initialization is skipped.

Example of python file:

.. code-block:: python
    :name: test_sdwatchdog

    import logging
    from time import sleep

    from aiomisc import entrypoint
    from aiomisc.service.sdwatchdog import SDWatchdogService


    if __name__ == '__main__':
        with entrypoint(SDWatchdogService()) as loop:
            pass


Example of systemd service file:

.. code-block:: ini

    [Service]
    # Activating the notification mechanism
    Type=notify

    # Command which should be started
    ExecStart=/home/mosquito/.venv/aiomisc/bin/python /home/mosquito/scratch.py

    # The time for which the program must send a watchdog notification
    WatchdogSec=5

    # Kill the process if it has stopped responding to the watchdog timer
    WatchdogSignal=SIGKILL

    # The service should be restarted on failure
    Restart=on-failure

    # Try to kill the process instead of cgroup
    KillMode=process

    # Trying to stop service properly
    KillSignal=SIGINT

    # Trying to restart service properly
    RestartKillSignal=SIGINT

    # Send SIGKILL when timeouts are exceeded
    FinalKillSignal=SIGKILL
    SendSIGKILL=yes


.. _process-service:

``ProcessService``
++++++++++++++++++

A base class for launching a function by a separate system process,
and by termination when the parent process is stopped.

.. code-block:: python

    from typing import Dict, Any

    import aiomisc.service

    # Fictional miner implementation
    from .my_miner import Miner


    class MiningService(aiomisc.service.ProcessService):
        bitcoin: bool = False
        monero: bool = False
        dogiecoin: bool = False

        def in_process(self) -> Any:
            if self.bitcoin:
                miner = Miner(kind="bitcoin")
            elif self.monero:
                miner = Miner(kind="monero")
            elif self.dogiecoin:
                miner = Miner(kind="dogiecoin")
            else:
                # Nothing to do
                return

            miner.do_mining()


    services = [
        MiningService(bitcoin=True),
        MiningService(monero=True),
        MiningService(dogiecoin=True),
    ]

    if __name__ == '__main__':
        with aiomisc.entrypoint(*services) as loop:
            loop.run_forever()


``RespawningProcessService``
++++++++++++++++++++++++++++

A base class for launching a function by a separate system process,
and by termination when the parent process is stopped, It's pretty
like `ProcessService` but have one difference when the process
unexpectedly exited this will be respawned.

.. code-block:: python

    import logging
    from typing import Any

    import aiomisc

    from time import sleep


    class SuicideService(aiomisc.service.RespawningProcessService):
        def in_process(self) -> Any:
            sleep(10)
            logging.warning("Goodbye mad world")
            exit(42)


    if __name__ == '__main__':
        with aiomisc.entrypoint(SuicideService()) as loop:
            loop.run_forever()
