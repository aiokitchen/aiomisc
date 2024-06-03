import logging
import socket
from functools import partial
from typing import Any, Iterable

import dnslib  # type: ignore[import-untyped]

from aiomisc.compat import sock_set_nodelay, sock_set_reuseport
from aiomisc.service import UDPServer

from .records import RecordType
from .store import DNSStore


log = logging.getLogger(__name__)


def socket_factory(binds: Iterable[str]) -> socket.socket:
    sock = socket.socket(socket.AF_UNSPEC, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setblocking(False)

    sock_set_reuseport(sock, True)
    sock_set_nodelay(sock)

    for bind in binds:
        if ":" in bind:
            address, str_port = bind.rsplit(":")
            port = int(str_port)
        else:
            address = "::"
            port = int(bind)
        log.info(
            "DNS server is listening on udp://%s:%s", address, port,
        )

        sock.bind((address, port))

    return sock


class DNSServer(UDPServer):
    store: DNSStore

    def __init__(
        self, store: DNSStore, binds: Iterable[str] = (), **kwargs: Any,
    ) -> None:
        self.make_socket = partial(socket_factory, binds)
        self.store = store
        super().__init__(**kwargs)

    async def handle_datagram(self, data: bytes, addr: tuple) -> None:
        record = dnslib.DNSRecord.parse(data)
        question: dnslib.DNSQuestion = record.get_q()
        reply = record.reply()
        query_name = str(question.get_qname())
        query_type = question.qtype

        records = self.store.query(query_name, RecordType(query_type))
        for rec in records:
            reply.add_answer(rec.rr(query_type))
        self.sendto(reply.pack(), addr)
