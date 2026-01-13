import asyncio
from abc import ABC, ABCMeta, abstractmethod
from collections.abc import Coroutine
from typing import Any, TypeVar

from ..context import Context, get_context
from ..utils import cancel_tasks

T = TypeVar("T")
CoroutineType = Coroutine[Any, Any, T]


class ServiceMeta(ABCMeta):
    def __new__(
        cls, name: str, bases: tuple, namespace: dict, **kwds: Any
    ) -> Any:
        instance = super().__new__(cls, name, bases, dict(namespace))

        for key in ("__async_required__", "__required__"):
            setattr(instance, key, frozenset(getattr(instance, key, ())))

        check_instance = all(
            asyncio.iscoroutinefunction(getattr(instance, method))
            for method in instance.__async_required__  # type: ignore
        )

        if not check_instance:
            raise TypeError(
                "Following methods must be coroutine functions",
                tuple(
                    f"{name}.{m}"
                    for m in instance.__async_required__  # type: ignore
                ),
            )

        return instance


class Service(metaclass=ServiceMeta):
    __async_required__: tuple[str, ...] = ("start", "stop")
    __required__: tuple[str, ...] = ()

    _instance_params: dict[str, Any]

    def __new__(cls, *args: Any, **kwargs: Any) -> "Service":
        instance = super().__new__(cls)
        instance._instance_params = {}
        return instance

    def __init__(self, **kwargs: Any):
        lost_kw = self.__required__ - kwargs.keys()
        if lost_kw:
            raise AttributeError("Absent attributes", lost_kw)

        self._set_params(**kwargs)
        self.__context: Context | None = None
        self.__start_event: asyncio.Event | None = None

    def __getattr__(self, key: str) -> Any:
        try:
            return self._instance_params[key]
        except KeyError as e:
            raise AttributeError(key) from e

    def __setattr__(self, key: str, value: Any) -> None:
        super().__setattr__(key, value)
        if key in self._instance_params:
            self._instance_params[key] = value

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
        self._instance_params = kwargs

        for name, value in kwargs.items():
            setattr(self, name, value)

    def __getstate__(self) -> dict[str, Any]:
        return self._instance_params

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._set_params(**state)

    @abstractmethod
    async def start(self) -> Any:
        raise NotImplementedError

    async def stop(self, exception: Exception | None = None) -> Any:
        pass


class TaskStoreBase(Service, ABC):
    def __init__(self, **kwargs: Any):
        self.tasks: set[asyncio.Task] = set()
        super().__init__(**kwargs)

    def create_task(self, coro: CoroutineType) -> asyncio.Task:
        task: asyncio.Task = self.loop.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def stop(self, exc: Exception | None = None) -> None:
        await cancel_tasks(self.tasks)


class SimpleServer(TaskStoreBase):
    def __init__(self, **kwargs: Any):
        self.server: asyncio.AbstractServer | None = None
        self.tasks: set[asyncio.Task] = set()
        super().__init__(**kwargs)

    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError

    async def stop(self, exc: Exception | None = None) -> None:
        await super().stop(exc)

        if self.server:
            self.server.close()


class SimpleClient(TaskStoreBase):
    @abstractmethod
    async def start(self) -> None:
        raise NotImplementedError
