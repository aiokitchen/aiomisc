import asyncio
from concurrent.futures import Future
from concurrent.futures import ProcessPoolExecutor as ProcessPoolExecutorBase
from multiprocessing import cpu_count
from typing import Any

from .compat import EventLoopMixin
from .counters import Statistic


class ProcessPoolStatistic(Statistic):
    processes: int
    done: int
    error: int
    success: int
    submitted: int
    sum_time: float


class ProcessPoolExecutor(ProcessPoolExecutorBase, EventLoopMixin):
    """
    Process pool executor with statistic

    Usage:

    .. code-block:: python

        from time import sleep
        from aiomisc import ProcessPoolExecutor

        # NOTE: blocking function must be defined at the top level
        # of the module to be able to be pickled and sent to the
        # child processes.
        def blocking_fn():
            sleep(1)
            return 42

        async def main():
            executor = ProcessPoolExecutor()
            the_answer = await executor.submit(blocking_fn)
            print("The answer is:", the_answer)

        asyncio.run(main())
    """

    DEFAULT_MAX_WORKERS = max((cpu_count(), 4))

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS, **kwargs: Any):
        """
        Initializes a new ProcessPoolExecutor instance.

        * ``max_workers``:
          The maximum number of processes that can be used to
          execute the given calls. If None or not given then
          as many worker processes will be created as the
          machine has processors.
        * ``mp_context``:
          A multiprocessing context to launch the workers. This
          object should provide SimpleQueue, Queue and Process.
          Useful to allow specific multiprocessing start methods.
        * ``initializer``:
          A callable used to initialize worker processes.
        * ``initargs``:
          A tuple of arguments to pass to the initializer.
        * ``max_tasks_per_child``:
          The maximum number of tasks a worker process
          can complete before it will exit and be replaced
          with a fresh worker process. The default of None
          means worker process will live as long as the
          executor. Requires a non-'fork' mp_context start
          method. When given, we default to using 'spawn'
          if no mp_context is supplied.
        """
        super().__init__(max_workers=max_workers, **kwargs)
        self._statistic = ProcessPoolStatistic()
        self._statistic.processes = max_workers

    def _statistic_callback(
        self,
        future: Future,
        start_time: float,
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """
        Callback for statistic
        """
        if future.exception():
            self._statistic.error += 1
        else:
            self._statistic.success += 1
        self._statistic.done += 1
        self._statistic.sum_time += loop.time() - start_time

    def submit(self, *args: Any, **kwargs: Any) -> Future:
        """
        Submit blocking function to the pool
        """
        loop = asyncio.get_running_loop()
        start_time = loop.time()
        future = super().submit(*args, **kwargs)
        self._statistic.submitted += 1
        future.add_done_callback(
            lambda f: self._statistic_callback(f, start_time, loop),
        )
        return future

    def __del__(self) -> None:
        """
        Cleanup resources
        """
        self.shutdown()
