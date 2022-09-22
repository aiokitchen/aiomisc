import asyncio
from abc import ABC, ABCMeta, abstractmethod
from typing import (
    Any, Coroutine, Dict, Generator, Optional, Set, Tuple, TypeVar, Union,
)

from ..context import Context, get_context
from ..utils import cancel_tasks


T = TypeVar("T")
CoroutineType = Union[Coroutine[Any, Any, T], Generator[Any, None, T]]


class ServiceMeta(ABCMeta):
    def __new__(
        cls, name: str, bases: Tuple, namespace: Dict, **kwds: Any
    ) -> Any:
        instance = super().__new__(
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

    __instance_params: Dict[str, Any]

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
        self.__instance_params = kwargs

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __getstate__(self) -> Dict[str, Any]:
        return self.__instance_params

    def __setstate__(self, state: Dict[str, Any]) -> None:
        self._set_params(**state)

    @abstractmethod
    async def start(self) -> Any:
        raise NotImplementedError

    async def stop(self, exception: Exception = None) -> Any:
        pass


class TaskStoreBase(Service, ABC):
    def __init__(self, **kwargs: Any):
        self.tasks: Set[asyncio.Task] = set()
        super().__init__(**kwargs)

    def create_task(self, coro: CoroutineType) -> asyncio.Task:
        task: asyncio.Task = self.loop.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.remove)
        return task

    async def stop(self, exc: Exception = None) -> None:
        await cancel_tasks(self.tasks)


class SimpleServer(TaskStoreBase):
    def __init__(self, **kwargs: Any):
        self.server: Optional[asyncio.AbstractServer] = None
        self.tasks: Set[asyncio.Task] = set()
        super().__init__(**kwargs)

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, exc: Exception = None) -> None:
        await super().stop(exc)

        if self.server:
            self.server.close()


class SimpleClient(TaskStoreBase):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError
