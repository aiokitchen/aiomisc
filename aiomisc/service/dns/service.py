import asyncio
import logging
from asyncio import StreamReader, StreamWriter
from struct import Struct
from typing import Optional, Tuple

import dnslib  # type: ignore[import-untyped]

from aiomisc.service import TCPServer, UDPServer

from .records import RecordType
from .store import DNSStore


log = logging.getLogger(__name__)


class DNSServer:
    store: DNSStore

    __proto__: str

    @staticmethod
    def get_edns_max_size(record: dnslib.DNSRecord) -> Optional[int]:
        for rr in record.ar:
            if rr.rtype != dnslib.QTYPE.OPT:
                continue
            return rr.edns_len
        return None

    def handle_request(
        self, addr: tuple, data: bytes, should_truncate: bool = False,
    ) -> Tuple[bytes, tuple]:
        record = dnslib.DNSRecord.parse(data)
        question: dnslib.DNSQuestion = record.get_q()
        reply = record.reply()
        query_name = str(question.get_qname())
        query_type = question.qtype

        try:
            log.debug(
                "Processing %s request from %r:\n%s\n",
                self.__proto__, addr, record,
            )
            edns_max_size = self.get_edns_max_size(record)
            if edns_max_size is not None:
                reply.add_ar(dnslib.EDNS0(udp_len=edns_max_size))

            records = self.store.query(query_name, RecordType(query_type))
            for rec in records:
                reply.add_answer(rec.rr(query_type))

            if not records:
                reply.header.rcode = dnslib.RCODE.NXDOMAIN

            log.debug(
                "Sending %s answer to %r:\n%s\n",
                self.__proto__, addr, reply,
            )

            reply_body = reply.pack()

            if len(reply_body) > 512:
                reply.header.tc = 1
                reply_body = reply.pack()

            if should_truncate:
                reply_body = reply_body[:edns_max_size]
        except Exception as e:
            log.exception(
                "Failed to process %s request from %r: %s",
                self.__proto__, addr, e,
            )
            reply = record.reply()
            reply.header.set_rcode(dnslib.RCODE.SERVFAIL)
            reply_body = reply.pack()

        return reply_body, addr


class UDPDNSServer(DNSServer, UDPServer):
    MAX_SIZE = 512

    store: DNSStore

    __required__ = ("store",)
    __proto__ = "UDP"

    async def handle_datagram(self, data: bytes, addr: tuple) -> None:
        self.sendto(
            *self.handle_request(
                data=data, addr=addr, should_truncate=True,
            ),
        )


TCP_HEADER_STRUCT: Struct = Struct("!H")


class TCPDNSServer(DNSServer, TCPServer):
    store: DNSStore

    __required__ = ("store",)

    __proto__ = "TCP"

    async def handle_client(
        self, reader: StreamReader, writer: StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        try:
            while True:
                data = await reader.readexactly(TCP_HEADER_STRUCT.size)
                if not data:
                    break
                length = TCP_HEADER_STRUCT.unpack(data)[0]
                packet = await reader.read(length)

                if not data:
                    break

                reply_body, _ = self.handle_request(data=packet, addr=addr)

                writer.write(TCP_HEADER_STRUCT.pack(len(reply_body)))
                writer.write(reply_body)
                await writer.drain()
        except asyncio.IncompleteReadError:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
