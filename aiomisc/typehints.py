from typing import TypeVar, Callable, Coroutine, Any, Union

Number = Union[int, float]

T = TypeVar("T")
DT = TypeVar("DT")

CoroutineFunctionType = Callable[..., Coroutine[Any, None, T]]
DecoratorType = Callable[[DT], DT]
