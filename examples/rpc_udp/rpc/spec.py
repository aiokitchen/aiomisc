from typing import Dict, Any, Optional

import msgspec


class Request(msgspec.Struct):
    id: int
    method: str
    params: Dict[str, Any]


class Error(msgspec.Struct):
    type: str
    args: Any


class Response(msgspec.Struct):
    id: int
    result: Optional[Any] = None
    error: Optional[Error] = None
