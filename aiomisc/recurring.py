import asyncio
import logging
from types import MappingProxyType
from typing import Any, Awaitable, Callable, Mapping, Tuple, Type, Union

from aiomisc import Statistic, utils


log = logging.getLogger(__name__)
ExceptionsType = Tuple[Type[Exception], ...]
CallbackType = Callable[..., Union[Awaitable[Any], Any]]
RecurringCallbackStrategy = Callable[
    ["RecurringCallback"],
    Union[int, float, Awaitable[int], Awaitable[float]],
]


class RecurringCallbackStatistic(Statistic):
    call_count: int
    done: int
    fail: int
    sum_time: float


class StrategyException(Exception):
    pass


class StrategyStop(StrategyException):
    """
    Strategy function might raise this exception as way to  stop recurring
    """
    pass


class StrategySkip(StrategyException):
    """
    Strategy function might raise this exception as way to skip current call
    """

    def __init__(self, next_attempt_delay: Union[int, float]):
        self.delay = next_attempt_delay


class RecurringCallback:
    __slots__ = ("func", "args", "kwargs", "name", "_statistic")

    def __init__(
        self, coroutine_func: CallbackType,
        *args: Any, **kwargs: Any
    ):
        self.func: Callable[..., Awaitable[Any]]
        self.args: Tuple[Any, ...]
        self.kwargs: Mapping[str, Any]
        self._statistic: RecurringCallbackStatistic

        self.name: str = repr(coroutine_func)
        self._statistic = RecurringCallbackStatistic(name=self.name)
        self.func = utils.awaitable(coroutine_func)
        self.args = args
        self.kwargs = MappingProxyType(kwargs)

    async def _exec(
        self,
        loop: asyncio.AbstractEventLoop,
        suppress_exceptions: ExceptionsType = (),
    ) -> None:
        self._statistic.call_count += 1
        delta: float = - loop.time()
        try:
            await self.func(*self.args, **self.kwargs)
        except suppress_exceptions:
            self._statistic.fail += 1
            return
        except asyncio.CancelledError:
            raise
        except Exception:
            self._statistic.fail += 1
            log.exception("Recurring task error:")
        else:
            self._statistic.done += 1
        finally:
            delta += loop.time()
            self._statistic.sum_time += delta

    async def _start(
        self,
        strategy: Callable[
            ["RecurringCallback"], Awaitable[Union[int, float]],
        ],
        loop: asyncio.AbstractEventLoop,
        *, shield: bool = False,
        suppress_exceptions: ExceptionsType = ()
    ) -> None:
        runner: Callable[..., Awaitable[Any]]

        while True:
            if loop.is_closed():
                return

            runner = self._exec
            if shield:
                runner = utils.shield(self._exec)

            try:
                delay: Union[int, float] = await strategy(self)
                if not isinstance(delay, (int, float)):
                    log.warning(
                        "Strategy %r returns wrong delay %r. Stopping.",
                        strategy, delay,
                    )
                    return
                if delay < 0:
                    log.warning(
                        "Strategy %r returns negative delay %r. "
                        "Zero delay will be used.",
                        strategy, delay,
                    )
                    delay = 0
            except StrategySkip as e:
                await asyncio.sleep(e.delay)
                continue
            except StrategyException:
                return

            await asyncio.sleep(delay)
            future = loop.create_future()
            task: asyncio.Task = asyncio.ensure_future(
                runner(
                    loop=loop,
                    suppress_exceptions=suppress_exceptions,
                ),
            )

            def on_done(task: asyncio.Task) -> None:
                if future.done():
                    return
                future.set_result(task)

            task.add_done_callback(on_done)

            try:
                await future
            except asyncio.CancelledError:
                if not task.done():
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                raise

    def start(
        self,
        strategy: RecurringCallbackStrategy,
        loop: asyncio.AbstractEventLoop = None, *,
        shield: bool = False,
        suppress_exceptions: ExceptionsType = ()
    ) -> asyncio.Task:
        loop = loop or asyncio.get_event_loop()
        return loop.create_task(
            self._start(
                strategy=utils.awaitable(strategy), loop=loop, shield=shield,
                suppress_exceptions=suppress_exceptions,
            ),
        )

    def __repr__(self) -> str:
        return "<%s(%s)>" % (self.__class__.__name__, self.name)
