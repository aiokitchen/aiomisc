import asyncio
from concurrent.futures._base import Executor, Future
from multiprocessing import Pool, cpu_count
import typing

from .typehints import T


CallbackType = typing.Callable[[T], None]
ResultType = typing.Any
CreateFutureResult = typing.Tuple[
    CallbackType[ResultType],
    CallbackType[BaseException],
    Future,
]


class ProcessPoolExecutor(Executor):
    def __init__(self, max_workers: int = max((cpu_count(), 4)),
                 **kwargs: typing.Any):
        self.__futures = set()   # type: typing.Set[Future[ResultType]]
        self.__pool = Pool(processes=max_workers, **kwargs)

    def _create_future(self) -> CreateFutureResult:
        loop = asyncio.get_event_loop()
        future = Future()   # type: Future[ResultType]

        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)

        def callback(result: ResultType) -> None:
            loop.call_soon_threadsafe(future.set_result, result)

        def errorback(exc: BaseException) -> None:
            loop.call_soon_threadsafe(future.set_exception, exc)

        return callback, errorback, future

    def submit(self, fn: typing.Callable[..., typing.Any],
               *args: typing.Any, **kwargs: typing.Any) -> Future[ResultType]:
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

        return future

    def shutdown(self, wait: bool = True) -> None:
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
