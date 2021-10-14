import asyncio
from typing import Any, Awaitable, Dict, Optional, Set, Tuple

from ..context import Context, get_context
from ..utils import cancel_tasks


class ServiceMeta(type):
    def __new__(
        cls, name: str, bases: Tuple, namespace: Dict, **kwds: Any
    ) -> Any:
        instance = type.__new__(
            cls, name, bases, dict(namespace),
        )

        for key in ("__async_required__", "__required__"):
            setattr(instance, key, frozenset(getattr(instance, key, ())))

        check_instance = all(
            asyncio.iscoroutinefunction(getattr(instance, method))
            for method in instance.__async_required__   # type: ignore
        )

        if not check_instance:
            raise TypeError(
                "Following methods must be coroutine functions",
                tuple(
                    "%s.%s" % (name, m)
                    for m in instance.__async_required__    # type: ignore
                ),
            )

        return instance


class Service(metaclass=ServiceMeta):
    __async_required__: Tuple[str, ...] = ("start", "stop")
    __required__: Tuple[str, ...] = ()

    def __init__(self, **kwargs: Any):
        lost_kw = self.__required__ - kwargs.keys()
        if lost_kw:
            raise AttributeError("Absent attributes", lost_kw)

        self._set_params(**kwargs)
        self.__context: Optional[Context] = None
        self.__start_event: Optional[asyncio.Event] = None

    @property
    def start_event(self) -> asyncio.Event:
        if self.__start_event is None:
            raise RuntimeError

        return self.__start_event

    @property
    def context(self) -> Context:
        if self.__context is None:
            self.__context = get_context()
        return self.__context

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        # noinspection PyAttributeOutsideInit
        self.loop = loop
        self.__start_event = asyncio.Event()

    def _set_params(self, **kwargs: Any) -> None:
        for name, value in kwargs.items():
            setattr(self, name, value)

    async def start(self) -> Any:
        raise NotImplementedError

    async def stop(self, exception: Exception = None) -> Any:
        pass


class SimpleServer(Service):
    def __init__(self, **kwargs: Any):
        self.server: Optional[asyncio.AbstractServer] = None
        self.tasks: Set[asyncio.Task] = set()
        super().__init__(**kwargs)

    def create_task(self, coro: Awaitable[Any]) -> asyncio.Task:
        task = self.loop.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.remove)
        return task

    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, exc: Exception = None) -> None:
        await cancel_tasks(self.tasks)

        if self.server:
            self.server.close()
