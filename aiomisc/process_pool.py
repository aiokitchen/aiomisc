import asyncio
from concurrent.futures._base import Executor
from multiprocessing import Pool, cpu_count


class ProcessPoolExecutor(Executor):
    def __init__(self, max_workers=max((cpu_count(), 4)), **kwargs):
        self.__futures = set()
        self.__pool = Pool(processes=max_workers, **kwargs)

    def _create_future(self):
        loop = asyncio.get_event_loop()
        future = loop.create_future()  # type: asyncio.Future

        self.__futures.add(future)
        future.add_done_callback(self.__futures.remove)

        def callback(result):
            loop.call_soon_threadsafe(future.set_result, result)

        def errorback(exc):
            loop.call_soon_threadsafe(future.set_exception, exc)

        return callback, errorback, future

    def submit(self, fn, *args, **kwargs):
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

    def shutdown(self, wait=True):
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

    def __del__(self):
        self.shutdown()
