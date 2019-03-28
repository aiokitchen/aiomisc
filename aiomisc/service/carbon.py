import re
import logging
from types import MappingProxyType
from typing import List     # NOQA

from aiocarbon.protocol.pickle import PickleClient
from aiocarbon.protocol.tcp import TCPClient
from aiocarbon.protocol.udp import UDPClient
from aiocarbon.storage import TotalStorage
from aiocarbon.setup import set_client

from aiomisc.periodic import PeriodicCallback
from aiomisc.service import Service


log = logging.getLogger(__name__)


def strip_carbon_ns(string):
    return re.sub(r'[^\w\d\-]+', '_', string).strip("_").lower()


PROTOCOLS = MappingProxyType({
    "udp": UDPClient,
    "tcp": TCPClient,
    "pickle": PickleClient,
})


class CarbonSender(Service):
    host = '127.0.0.1'          # type: str
    port = 2003                 # type: int
    send_interval = 5           # type: int
    protocol = 'udp'            # type: str
    namespace = ''              # type: List[str]
    storage = TotalStorage
    _handle = None              # type: PeriodicCallback

    async def start(self):
        namespace = ".".join(
            strip_carbon_ns(item) for item in self.namespace
        )

        client = PROTOCOLS[self.protocol](
            self.host,
            self.port,
            namespace=namespace,
            storage=self.storage(),
            loop=self.loop
        )

        set_client(client)

        self._handle = PeriodicCallback(client.send)
        self._handle.start(self.send_interval, loop=self.loop)
        log.info(
            'Periodic carbon metrics sender started. Send to %s://%s:%d with '
            'interval %rs', self.protocol, self.host, self.port,
            self.send_interval)

    async def stop(self, *_):
        self._handle.stop()
