import asyncio
from concurrent.futures import Executor
from multiprocessing import Pool, cpu_count
from time import monotonic
from typing import Any, Callable, Set, Tuple, TypeVar

from .counters import Statistic


T = TypeVar("T")
FuturesSet = Set[asyncio.Future]
_CreateFutureType = Tuple[
    Callable[[T], None],
    Callable[[T], None],
    asyncio.Future,
]


class ProcessPoolStatistic(Statistic):
    processes: int
    done: int
    error: int
    success: int
    submitted: int
    sum_time: float


class ProcessPoolExecutor(Executor):
    DEFAULT_MAX_WORKERS = max((cpu_count(), 4))

    def __init__(self, max_workers: int = DEFAULT_MAX_WORKERS, **kwargs: Any):
        self.__futures = set()      # type: FuturesSet
        self.__pool = Pool(processes=max_workers, **kwargs)
        self._statistic = ProcessPoolStatistic()
        self._statistic.processes = max_workers

    def _create_future(self) -> _CreateFutureType:
        loop = asyncio.get_event_loop()
        future = loop.create_future()  # type: asyncio.Future

        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)
        start_time = monotonic()

        def callback(result: T) -> None:
            self._statistic.success += 1
            self._statistic.done += 1
            self._statistic.sum_time += monotonic() - start_time
            loop.call_soon_threadsafe(future.set_result, result)

        def errorback(exc: T) -> None:
            self._statistic.error += 1
            self._statistic.done += 1
            self._statistic.sum_time += monotonic() - start_time
            loop.call_soon_threadsafe(future.set_exception, exc)

        return callback, errorback, future

    def submit(           # type: ignore
        self, fn: Callable[..., T],
        *args: Any, **kwargs: Any
    ) -> asyncio.Future:
        """
        Submit blocking function to the pool
        """
        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        callback, errorback, future = self._create_future()

        self.__pool.apply_async(
            fn,
            args=args,
            kwds=kwargs,
            callback=callback,
            error_callback=errorback,
        )

        self._statistic.submitted += 1
        return future

    # noinspection PyMethodOverriding
    def shutdown(self, wait: bool = True) -> None:  # type: ignore
        if not self.__pool:
            return

        self.__pool.terminate()

        for f in self.__futures:
            if f.done():
                continue
            f.set_exception(asyncio.CancelledError())

        if wait:
            self.__pool.join()

        self.__pool.close()

    def __del__(self) -> None:
        self.shutdown()
