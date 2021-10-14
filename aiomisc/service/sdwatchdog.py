import os
import socket
from typing import Any, Optional

from .udp import UDPServer


class SDNotifyService(UDPServer):
    @classmethod
    def create(cls) -> Optional["SDNotifyService"]:
        addr = os.getenv('NOTIFY_SOCKET')
        if addr is None:
            return None

        if addr[0] == '@':
            addr = '\0' + addr[1:]

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.connect(addr)

        return cls(sock=sock)

    def handle_datagram(self, data: bytes, addr: tuple) -> None:
        self.sendto()
