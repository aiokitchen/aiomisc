import asyncio
import os
import platform
import socket
from collections import Counter, defaultdict, deque
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Deque, Tuple
from collections.abc import MutableMapping

import pytest

import aiomisc
from aiomisc import bind_socket
from aiomisc.service import UDPServer, sdwatchdog

pytestmark = pytest.mark.skipif(
    platform.system() == "Windows", reason="Unix only tests"
)


def test_sdwatchdog_service(event_loop):
    with TemporaryDirectory(dir="/tmp") as tmp_dir:
        tmp_path = Path(tmp_dir)
        sock_path = str(tmp_path / "notify.sock")

        packets: deque[tuple[Any, ...]] = deque()

        class FakeSystemd(UDPServer):
            async def handle_datagram(
                self, data: bytes, addr: tuple[Any, ...]
            ) -> None:
                key: str
                value: str
                key, value = data.decode().split("=", 1)
                packets.append(((key, value), addr))

        with bind_socket(
            socket.AF_UNIX,
            socket.SOCK_DGRAM,
            address=sock_path,
            reuse_port=False,
        ) as sock:
            try:
                os.environ["NOTIFY_SOCKET"] = sock_path
                os.environ["WATCHDOG_USEC"] = "100000"

                service = sdwatchdog.SDWatchdogService(
                    watchdog_interval=sdwatchdog._get_watchdog_interval()
                )

                assert service.watchdog_interval == 0.1

                with aiomisc.entrypoint(
                    FakeSystemd(sock=sock), service, loop=event_loop
                ):
                    event_loop.run_until_complete(asyncio.sleep(1))
            finally:
                for key in ("NOTIFY_SOCKET", "WATCHDOG_USEC"):
                    os.environ.pop(key)

    assert packets
    messages_count: MutableMapping[str, int] = Counter()
    messages = defaultdict(set)

    for (key, value), sender in packets:
        assert key
        assert value
        messages_count[key] += 1
        messages[key].add(value)

    assert 5 < messages_count["WATCHDOG"] < 25
    assert messages_count["STATUS"] == 2
    assert messages_count["WATCHDOG_USEC"] == 1
    assert tuple(messages["WATCHDOG_USEC"])[0] == "100000"
