import logging
import re
import typing as t  # noqa
from types import MappingProxyType

from aiocarbon.protocol.pickle import PickleClient  # type: ignore
from aiocarbon.protocol.tcp import TCPClient  # type: ignore
from aiocarbon.protocol.udp import UDPClient  # type: ignore
from aiocarbon.setup import set_client  # type: ignore
from aiocarbon.storage import TotalStorage  # type: ignore

from aiomisc.periodic import PeriodicCallback
from aiomisc.service import Service


log = logging.getLogger(__name__)


def strip_carbon_ns(string: str) -> str:
    return re.sub(r"[^\w\d\-]+", "_", string).strip("_").lower()


PROTOCOLS = MappingProxyType({
    "udp": UDPClient,
    "tcp": TCPClient,
    "pickle": PickleClient,
})


class CarbonSender(Service):
    host = "127.0.0.1"          # type: str
    port = 2003                 # type: int
    send_interval = 5           # type: int
    protocol = "udp"            # type: str
    namespace = ("",)           # type: t.Iterable[str]
    storage = TotalStorage
    _handle = None              # type: PeriodicCallback

    async def start(self) -> None:
        namespace = ".".join(
            strip_carbon_ns(item) for item in self.namespace
        )

        client = PROTOCOLS[self.protocol](
            self.host,
            self.port,
            namespace=namespace,
            storage=self.storage(),
        )

        set_client(client)

        self._handle = PeriodicCallback(client.send)
        self._handle.start(self.send_interval, loop=self.loop)
        log.info(
            "Periodic carbon metrics sender started. Send to %s://%s:%d with "
            "interval %rs", self.protocol, self.host, self.port,
            self.send_interval,
        )

    async def stop(self, exc: Exception = None) -> None:
        self._handle.stop()
