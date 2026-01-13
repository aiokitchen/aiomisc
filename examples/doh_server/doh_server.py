#!/usr/share/python3/doh/bin/python3
import logging

import aiohttp
import argclass
from yarl import URL

import aiomisc
from aiomisc.service.sdwatchdog import SDWatchdogService
from aiomisc.service.udp import UDPServer

log = logging.getLogger(__name__)


class Parser(argclass.Parser):
    address: str = "127.0.0.1"
    port: int = 25353
    log_level = argclass.LogLevel
    doh_url: URL = URL("https://1.1.1.1/dns-query")


class DNSUDPService(UDPServer):
    url: URL
    session: aiohttp.ClientSession

    async def handle_datagram(self, data: bytes, addr: tuple) -> None:
        request = self.session.post(
            self.url,
            data=data,
            headers={
                aiohttp.hdrs.ACCEPT: "application/dns-message",
                aiohttp.hdrs.CONTENT_TYPE: "application/dns-message",
            },
        )
        async with request as response:
            log.debug("Handling request from %r", addr)
            self.sendto(await response.read(), addr)

    async def start(self) -> None:
        await super().start()
        self.session = aiohttp.ClientSession()

    async def stop(self, exc: Exception = None) -> None:
        await self.session.close()
        await super().stop(exc)


if __name__ == "__main__":
    parser = Parser(auto_env_var_prefix="DOH_")
    parser.parse_args()

    services = [
        DNSUDPService(
            address=parser.address, port=parser.port, url=parser.doh_url
        ),
        SDWatchdogService(),
    ]

    with aiomisc.entrypoint(*services, log_level=parser.log_level) as loop:
        loop.run_forever()
