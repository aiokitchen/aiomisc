import asyncio
from contextvars import ContextVar
from typing import Any, Generic, Optional, TypeVar


CT = TypeVar("CT", bound=Any)


class StrictContextVar(Generic[CT]):
    def __init__(self, name: str, exc: Exception):
        self.exc: Exception = exc
        self.context_var: ContextVar = ContextVar(name)

    def get(self) -> CT:
        value: Optional[CT] = self.context_var.get(None)
        if value is None:
            raise self.exc
        return value

    def set(self, value: CT) -> None:
        self.context_var.set(value)


EVENT_LOOP: StrictContextVar[asyncio.AbstractEventLoop] = StrictContextVar(
    "EVENT_LOOP", RuntimeError("no current event loop is set"),
)
