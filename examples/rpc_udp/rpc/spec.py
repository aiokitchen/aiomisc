from typing import Any, Dict, Optional

import msgspec


class Request(msgspec.Struct):
    id: int
    method: str
    params: dict[str, Any]


class Error(msgspec.Struct):
    type: str
    args: Any


class Response(msgspec.Struct):
    id: int
    result: Any | None = None
    error: Error | None = None


class Payload(msgspec.Struct):
    request: Request | None = None
    response: Response | None = None
