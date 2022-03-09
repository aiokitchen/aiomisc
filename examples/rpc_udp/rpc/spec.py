from typing import Any, Dict, Optional

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


class Payload(msgspec.Struct):
    request: Optional[Request] = None
    response: Optional[Response] = None
