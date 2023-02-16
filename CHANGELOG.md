Changelog
=========

This document describes the changes that have occurred in the
releases of this library.

The story is not written from the very beginning, but from
the moment when we feel the need to start it. You can always
view the commit history if you couldn't find something
in this document.

17.0.x
------

In this release, the aiomisc_pytest module has been mostly removed, and has
been separated into a separate package. This is the main, breaking change
of this release.

* Dynamic running of services see
  [also](https://aiomisc.readthedocs.io/en/latest/entrypoint.html#dynamic-running-of-services)
* New `aiomisc.entrypoint.get_current()` function returns current
  running entrypoint
* Removed `aiomisc_pytest` because is now a separate package
  [aiomisc-pytest](https://pypi.org/project/aiomisc-pytest/)
* `entrypoint` class is final now.
* Instance ordering not guaranteed in `Entrypoint.services` method
* The main function in `aiomisc_worker/forking.py` returns 0 when keyboard
  interrupt received

16.3.x
------

* Migrate to poetry #154
  * Use `poem-plugins` for creating `aiomisc/version.py` file and bump version
    when publishing.
  * some non-public imports might be broken, mainly typing, and the
   `aiomisc.io` module
  * Buffered log handler in `aiomisc.log`, is now correct finalize when an
    entrypoint stops. This is useful if the program uses multiple entrypoints
    while the program is running, and especially in tests.
  * Lots of changes in `aiomisc.io` module:
    * Support stream compression for opening files with:
      * `GZIP` - compressed files
      * `LZMA` - compressed files
      * `BZ2` - compressed files
  * Added `aiohttp_asgi` objects to `__all__` in `aiomisc.service.asgi`
  * `aiomisc.Service` subclasses is now can be serialized with `pickle`
  * Improves typing for:
    * `aiomisc.io`
    * `aiomisc.pool`
    * `aiomisc.service.udp`
    * `aiomisc.worker_pool.WorkerPool`
* Improve documentation

16.2.x
------

* Remove code from `aiomisc_log.formatter.journald` and move it into the
  3rd-party library
  [logging-journald](https://pypi.org/project/logging-journald)

16.1.x
------

* `threaded_iterable` internal implementation was reworked, it's a speed-up
  the functions which `yield` lots of items.
* `threaded_iterable_separate` did not create a separate thread.

16.0.x
------

* Added `RecurringCallback`
* Rewritten `PeriodicCallback` and `CronCallback` using `RecurringCallback`

15.9.x
------

* Threaded iterable has been optimized and would not create too
  much asyncio.Task instances.
* Sentry handler for python3.10

15.8.x
------

* `WorkerPool` reworked and now spawning processes  with `os.fork` on
  UNIX. This makes benefits on initializer has been passed.
  The allocated after initializer completion memory will be shared
  between processes with CoW.

15.7.x
------

* tcp and tls client services
* python<3.10 fixes
* retry connection attempts for client services
* rewrite rpc example with modern msgspec and client services
* `bind_port` will choose a free port when port passed as 0
* `aiomisc_unused_port_factory` is now the fixture just detach but not close
  just created socket and port isn't free and not be used twice but
  `bind_socket` function will be able to bind it.
* Fix `asyncbackoff` type annotations

15.6.x
------

* Fix tests
* Fix ``aiomisc.run`` in python 3.10
* Changed behavior in default event loop creation. In previous releases the
  function ``aiomisc.utils.create_default_event_loop()`` silently closes
  already created event loop. Now it checks is current event loop running,
  and raises an ``RuntimeError`` in this case.


15.5.x
------

* #126 reorder shutdown routines
* #128 session-scope agen fixture

15.4.x
------

* Added `RespawningProcessService` service class
* `Service` instances are now serializable by pickle.
* `PeriodicService` now checks the `interval` argument before starting.
* `entrypoint` not failing to stop when service instance implements
  `.stop()` method not properly.

15.3.x
------

* Tests for `JournaldLogHandler` and `SDWatchdogService` has been written
* `loop.sock_sendall` now used for `SDWatchdogService`

15.2.x
------

* Added `aiomisc.service.RespawningProcessService` for running python function
  in separate process and restart it when exiting.
* Rewrite `aiomisc.WorkerPool` using `multiprocessing.Process`
  instead of `subprocess.Popen`.
* `aiomisc.ServiceMeta` is now inherited from `abc.ABCMeta`. It means
* fixed (cron): is now set current datetime as start point #120
* `aiomisc.ServiceMeta` is now inherited from `abc.ABCMeta`. It means
  the decorations like `@abc.abstractmethod` will work with service classes.
* Added `aiomisc.service.ProcessService` for running python function in
  separate process.
* Change order of detection for `aiomisc_log.LogFormat.default()` in case
  the stderr is not a tty. Fixes `journald` formatter auto detection.
* Rewritten `aiomisc.iterator_wrapper.IteratorWrapper`  to avoid unnecessary
  context switches. Now, `__in_thread` method switches only when writing is
  possible instead of retrying every 100ms.

15.1.x
------

* Refactored `aiomisc.thread_pool.ThreadPoolExecutor`

15.0.x
------

* Split `aiomisc` into three python packages:
    * `aiomisc` - still contains entrypoint, services, etc.
    * `aiomisc_log` - logging related code.
    * `aiomisc_worket` - worker-pools worker related code/
* split plugins related code to `aiomisc.plugins` module from `__init__.py`
* `port=0` is a default for `aiomisc.utils.bind_socket()`
* `aiomisc.run()` function for running coroutine
  similar like `asuncio.run` but does all entrypoint work:
    * start services
    * logging configuration
    * creating thread-pool etc.
* replace `time.monotonic()` to `loop.time()` for:

    * `aiosmic.aggregate` module
    * `aiomisc.backoff` module
    * `aiomisc.cron` module
    * `aiomisc.pool` module
    * `aiomisc.process_pool` module

  It reduces system calls and slightly improves performance.
* Used to modern syntax old python 3.5 `# type:` hints.
* Added `__slots__` to `aiomisc.counters.Metric`
  and `aiomisc.counters.Statistic`
* Added entrypoint configuration from environment variables:
    * `AIOMISC_LOG_LEVEL`
    * `AIOMISC_LOG_FORMAT`
    * `AIOMISC_LOG_CONFIG`
    * `AIOMISC_LOG_FLUSH`
    * `AIOMISC_LOG_BUFFERING`
    * `AIOMISC_LOG_BUFFER`
    * `AIOMISC_POOL_SIZE`
* Added `aiomisc.entrypoint.POST_START` and
  `aiomisc.entrypoint.PRE_STOP` signals.
* Python 3.10 compatibility
* Changed logging configuration behavior, now uncaught exceptions will be
  passed to root handler and log formatter which configured by
  `aiomisc.log.basic_config()` function. Asyncio uncaught loop exceptions
  will have similar behavior.
* `python -m aiomisc.plugins` will show available plugins.
* `aiomisc.service.sdwatchdog.SDWatchdogService` - The service allows you to
  run the application under systemd. The service automatically detects the
  systemd watchdog timer and sends notifications to it.
* Fixed `aiomisc.sercice.TLSServer` compatibility for python 3.10
* Used `asyncio.get_running_loop` instead of deprecated in 3.10
  `asyncio.get_event_loop`
* `aiomisc.utils.run_in_executor` now returns `Awaitable[Any]`
  instead of `asuncio.Future`. This is because there is no way to create a
  `Future` outside of the running event loop using only
  `asyncio.get_running_loop`. These changes return type for functions
  wrapped by `threaded`.
* `AIOMISC_NO_PLUGINS` environment variable now disable loading any
  aiomisc plugin.
* Added new log formatters:

    * `rich` and `rich_tb` - requires installed `rich` library. `rich_tb`
      formats tracebacks using `rich`.
    * `journald` - write logs to journald.

* `aiomisc_log.formatter.journald` it's a logging handler for journald.
* Added `aiomisc.log.LogFormat.default()` and `aiomisc.log.LogLevel.default()`
  methods.
  `aiomisc.log.LogFormat.default()` - detects the environment. In case
  the application running under systemd returns `journald`, when `rich`
  has been installed the `rich` will be returned, otherwise `color`.
* Removed `async_generator` module support. Because python 3.5 is not
  supported anymore.
* Fixed "IO operation on closed file" error in pytest plugin.
* Refactored `get_unused_port` function and
  `aiomisc_unused_port_factory` fixture
* Added `aiomisc_socket_factory` fixture which returns port number
  and socket object pair.
* Added tests for documentation examples through `pytest-rst` module
* Added explanations for choosing module to perform Asynchronous files
  operations in the documentation.
