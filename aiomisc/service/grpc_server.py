import asyncio
import logging
import re
import sys
from concurrent.futures import Executor
from types import MappingProxyType
from typing import Any, Optional, Sequence, Set, Tuple

from .base import Service


try:
    import grpc.aio
except ImportError as e:
    raise ImportError(
        "You must install 'grpcio' manually or using extras 'aiomisc[grpc]'",
    ) from e

log = logging.getLogger(__name__)

if sys.version_info >= (3, 9):
    PortFuture = asyncio.Future[int]
else:
    PortFuture = asyncio.Future


class GRPCService(Service):
    GRACEFUL_STOP_TIME: float = 60.

    _ADDRESS_REGEXP = re.compile(
        r"(?P<address>(\[((([([0-9a-fA-F:]*)+)])?|([\w.]+))):(\d+)",
    )

    _server: grpc.aio.Server
    _server_args: MappingProxyType
    _insecure_ports: Set[Tuple[str, PortFuture]]
    _secure_ports: Set[Tuple[str, grpc.ServerCredentials, PortFuture]]

    def __init__(
        self, *,
        migration_thread_pool: Optional[Executor] = None,
        handlers: Optional[Sequence[grpc.GenericRpcHandler]] = None,
        interceptors: Optional[Sequence[Any]] = None,
        options: Optional[Sequence[Tuple[str, Any]]] = None,
        maximum_concurrent_rpcs: Optional[int] = None,
        compression: Optional[grpc.Compression] = None,
        **kwds: Any,
    ):
        self._server_args = MappingProxyType({
            "compression": compression,
            "handlers": handlers,
            "interceptors": interceptors,
            "maximum_concurrent_rpcs": maximum_concurrent_rpcs,
            "migration_thread_pool": migration_thread_pool,
            "options": options,
        })
        self._services: Set[grpc.GenericRpcHandler] = set()
        self._insecure_ports = set()
        self._secure_ports = set()
        super().__init__(**kwds)

    @classmethod
    def _log_port(cls, msg: str, address: str, bind_port: Any) -> None:
        match: Optional[re.Match] = cls._ADDRESS_REGEXP.match(address)

        if match is not None:
            groups = match.groupdict()
            address = groups["address"]

        log.info("%s: grpc://%s:%s", msg, address, bind_port)

    async def start(self) -> None:
        self._server = grpc.aio.server(**self._server_args)

        for address, future in self._insecure_ports:
            port = self._server.add_insecure_port(address)
            future.set_result(port)
            self._log_port("Listening insecure address", address, port)

        for address, credentials, future in self._secure_ports:
            port = self._server.add_secure_port(address, credentials)
            future.set_result(port)
            self._log_port("Listening secure address", address, port)

        self._server.add_generic_rpc_handlers(tuple(self._services))
        await self._server.start()

    async def stop(self, exception: Optional[Exception] = None) -> None:
        await self._server.stop(self.GRACEFUL_STOP_TIME)

    def add_generic_rpc_handlers(
        self, generic_rpc_handlers: Sequence[grpc.GenericRpcHandler],
    ) -> None:
        for service in generic_rpc_handlers:
            self._services.add(service)

    def add_insecure_port(self, address: str) -> PortFuture:
        future: PortFuture = asyncio.Future()
        self._insecure_ports.add((address, future))
        return future

    def add_secure_port(
        self, address: str,
        server_credentials: grpc.ServerCredentials,
    ) -> PortFuture:
        future: PortFuture = asyncio.Future()
        self._secure_ports.add((address, server_credentials, future))
        return future
