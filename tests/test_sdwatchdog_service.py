import asyncio
import os
from collections import deque, Counter, defaultdict
from pathlib import Path
from socket import AF_UNIX, SOCK_DGRAM
from tempfile import TemporaryDirectory

import pytest

import aiomisc
from aiomisc import bind_socket
from aiomisc.service import UDPServer
from aiomisc.service import sdwatchdog

pytestmark = pytest.mark.catch_loop_exceptions


def test_sdwatchdog_service(loop):
    with TemporaryDirectory(dir="/tmp") as tmp_dir:
        tmp_path = Path(tmp_dir)
        sock_path = str(tmp_path / "notify.sock")

        packets = deque()

        class FakeJournald(UDPServer):
            def handle_datagram(self, data: bytes, addr: tuple) -> None:
                packets.append((data.decode().split("=", 1), addr))

        with bind_socket(AF_UNIX, SOCK_DGRAM, address=sock_path) as sock:
            try:
                os.environ['NOTIFY_SOCKET'] = sock_path
                os.environ['WATCHDOG_USEC'] = "100000"

                service = sdwatchdog.SDWatchdogService(
                    watchdog_interval=sdwatchdog._get_watchdog_interval()
                )

                assert service.watchdog_interval == 0.1

                with aiomisc.entrypoint(
                    FakeJournald(sock=sock), service, loop=loop
                ):
                    loop.run_until_complete(asyncio.sleep(1))
            finally:
                for key in ('NOTIFY_SOCKET', 'WATCHDOG_USEC'):
                    os.environ.pop(key)

    assert packets
    messages_count = Counter()
    messages = defaultdict(set)

    for (key, value), sender in packets:
        assert key
        assert value
        messages_count[key] += 1
        messages[key].add(value)

    assert 5 < messages_count['WATCHDOG'] < 25
    assert messages_count['STATUS'] == 2
    assert messages_count['WATCHDOG_USEC'] == 1
    assert tuple(messages['WATCHDOG_USEC'])[0] == '100000'
