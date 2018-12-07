import asyncio
from functools import wraps
from time import monotonic
from typing import Union, TypeVar


Number = Union[int, float]
T = TypeVar('T')


class timeout:
    def __init__(self, timeout):
        self.timeout = timeout

    def __call__(self, func: T) -> T:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError("Function is not a coroutine function")

        async def awaiter(task):
            await task

        def cancel(loop, task: asyncio.Task, expired: asyncio.Event = None):
            if task.done():
                return

            task.cancel()

            if expired:
                expired.set()

            return loop.create_task(awaiter(task))

        @wraps(func)
        async def wrap(*args, **kwargs):
            try:
                loop = asyncio.get_event_loop()
                expired = asyncio.Event(loop=loop)

                # noinspection PyCallingNonCallable
                task = loop.create_task(
                    func(*args, **kwargs)
                )   # type: asyncio.Task

                loop.call_later(self.timeout, cancel, loop, task, expired)

                try:
                    return await task
                except asyncio.CancelledError as e:
                    cancel(loop, task, None)
                    if expired.is_set():
                        raise asyncio.TimeoutError from e
                    raise

            except Exception as e:
                print(monotonic(), 'inner', repr(e))
                raise

        return wrap
