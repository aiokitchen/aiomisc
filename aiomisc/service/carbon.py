import re
from types import MappingProxyType
from typing import List     # NOQA

from aiocarbon.protocol.pickle import PickleClient
from aiocarbon.protocol.tcp import TCPClient
from aiocarbon.protocol.udp import UDPClient
from aiocarbon.setup import set_client

from aiomisc.periodic import PeriodicCallback
from aiomisc.service import Service


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
    _handle = None              # type: PeriodicCallback

    async def start(self):
        namespace = ".".join(
            strip_carbon_ns(item) for item in self.namespace
        )

        client = PROTOCOLS[self.protocol](
            self.host,
            self.port,
            namespace=namespace,
            loop=self.loop
        )

        set_client(client)

        self._handle = PeriodicCallback(client.send)
        self._handle.start(self.send_interval, loop=self.loop)

    async def stop(self, *_):
        self._handle.stop()
