import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Hashable, Iterable, List

import dnslib  # type: ignore[import-untyped]


class RecordType(enum.IntEnum):
    A = 1
    A6 = 38
    AAAA = 28
    AFSDB = 18
    ANY = 255
    APL = 42
    AXFR = 252
    CAA = 257
    CDNSKEY = 60
    CDS = 59
    CERT = 37
    CNAME = 5
    CSYNC = 62
    DHCID = 49
    DLV = 32769
    DNAME = 39
    DNSKEY = 48
    DS = 43
    EUI48 = 108
    EUI64 = 109
    HINFO = 13
    HIP = 53
    HIP_AC = 55
    HTTPS = 65
    IPSECKEY = 45
    IXFR = 251
    KEY = 25
    KX = 36
    LOC = 29
    MX = 15
    NAPTR = 35
    NS = 2
    NSEC = 47
    NSEC3 = 50
    NSEC3PARAM = 51
    NULL = 10
    OPENPGPKEY = 61
    OPT = 41
    PTR = 12
    RP = 17
    RRSIG = 46
    SIG = 24
    SOA = 6
    SPF = 99
    SRV = 33
    SSHFP = 44
    SVCB = 64
    TA = 32768
    TKEY = 249
    TLSA = 52
    TSIG = 250
    TXT = 16
    URI = 256
    ZONEMD = 63


class DNSClass(enum.IntEnum):
    IN = 1
    CS = 2
    CH = 3
    Hesiod = 4
    NONE = 254
    ASTERISK = 255


class RD(dnslib.RD, Hashable, ABC):
    def __hash__(self) -> int:
        return hash(self.data)

    @classmethod
    @abstractmethod
    def create(cls, *args: Any, **kwargs: Any) -> "DNSRecord":
        raise NotImplementedError


@dataclass(frozen=True)
class DNSRecord:
    name: str
    type: RecordType
    data: RD
    cls: DNSClass = field(default=DNSClass.IN)
    ttl: int = field(default=3600, compare=False)

    def rr(self, query_type: int) -> dnslib.RR:
        return dnslib.RR(
            rname=self.name,
            rtype=query_type,
            rclass=self.cls,
            ttl=self.ttl,
            rdata=self.data,
        )


class A(dnslib.A, RD):
    @classmethod
    def create(cls, name: str, ip: str, ttl: int = 3600) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.A,
            data=cls(ip),
            ttl=ttl,
        )


class AAAA(dnslib.AAAA, RD):
    @classmethod
    def create(cls, name: str, ipv6: str, ttl: int = 3600) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.AAAA,
            data=cls(ipv6),
            ttl=ttl,
        )


class RDLabel(RD):
    label: bytes
    __type__: RecordType

    @classmethod
    def create(cls, name: str, label: str, ttl: int = 3600) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=cls.__type__,
            data=cls(label),
            ttl=ttl,
        )

    def __hash__(self) -> int:
        return hash(self.label)


class CNAME(dnslib.CNAME, RDLabel):
    __type__ = RecordType.CNAME


class NS(dnslib.NS, RDLabel):
    __type__ = RecordType.NS


class PTR(dnslib.PTR, RDLabel):
    __type__ = RecordType.PTR


class DNAME(dnslib.DNAME, RDLabel):
    __type__ = RecordType.DNAME


class MX(dnslib.MX, RD):
    @classmethod
    def create(
        cls, name: str, exchange: str, preference: int, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.MX,
            data=cls(exchange, preference),
            ttl=ttl,
        )


class TXT(dnslib.TXT, RD):
    @classmethod
    def create(cls, name: str, text: str, ttl: int = 3600) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.TXT,
            data=cls(text),
            ttl=ttl,
        )


class SOA(dnslib.SOA, RD):
    @classmethod
    def create(
        cls, name: str, mname: str, rname: str, serial: int,
        refresh: int, retry: int, expire: int, minimum: int,
        ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.SOA,
            data=cls(
                mname, rname,
                (serial, refresh, retry, expire, minimum),
            ),
            ttl=ttl,
        )


class SRV(dnslib.SRV, RD):
    @classmethod
    def create(
        cls, name: str, priority: int, weight: int, port: int,
        target: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.SRV,
            data=cls(priority, weight, port, target),
            ttl=ttl,
        )


class CAA(dnslib.CAA, RD):
    @classmethod
    def create(
        cls, name: str, flags: int, tag: str, value: str,
        ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.CAA,
            data=cls(flags, tag, value),
            ttl=ttl,
        )


class NAPTR(dnslib.NAPTR, RD):
    @classmethod
    def create(
        cls, name: str, order: int, preference: int, flags: str,
        service: str, regexp: str, replacement: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.NAPTR,
            data=cls(order, preference, flags, service, regexp, replacement),
            ttl=ttl,
        )


class DS(dnslib.DS, RD):
    @classmethod
    def create(
        cls, name: str, key_tag: int, algorithm: int, digest_type: int,
        digest: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.DS,
            data=cls(key_tag, algorithm, digest_type, digest),
            ttl=ttl,
        )


class DNSKEY(dnslib.DNSKEY, RD):
    @classmethod
    def create(
        cls, name: str, flags: int, protocol: int, algorithm: int,
        key: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.DNSKEY,
            data=cls(flags, protocol, algorithm, key),
            ttl=ttl,
        )


class RRSIG(dnslib.RRSIG, RD):
    @classmethod
    def create(
        cls, name: str, type_covered: int, algorithm: int, labels: int,
        original_ttl: int, expiration: int, inception: int, key_tag: int,
        signer: str, signature: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.RRSIG,
            data=cls(
                type_covered, algorithm, labels, original_ttl, expiration,
                inception, key_tag, signer, signature,
            ),
            ttl=ttl,
        )


class NSEC(dnslib.NSEC, RD):
    @classmethod
    def create(
        cls, name: str, next_domain: str,
        rrtypes: Iterable[int], ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.NSEC,
            data=cls(next_domain, list(rrtypes)),
            ttl=ttl,
        )


class HTTPS(dnslib.HTTPS, RD):
    @classmethod
    def create(
        cls, name: str, priority: int, target: str,
        params: List[str], ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.HTTPS,
            data=cls(priority, target, params),
            ttl=ttl,
        )


class LOC(dnslib.LOC, RD):
    @classmethod
    def create(
        cls, name: str, latitude: float, longitude: float,
        altitude: float, size: float, h_precision: float,
        v_precision: float, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.LOC,
            data=cls(
                latitude, longitude, altitude, size, h_precision, v_precision,
            ),
            ttl=ttl,
        )


class RP(dnslib.RP, RD):
    @classmethod
    def create(
        cls, name: str, mbox: str, txt: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.RP,
            data=cls(mbox, txt),
            ttl=ttl,
        )


class TLSA(dnslib.TLSA, RD):
    @classmethod
    def create(
        cls, name: str, usage: int, selector: int, mtype: int, cert: str,
        ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.TLSA,
            data=cls(usage, selector, mtype, cert),
            ttl=ttl,
        )


class SSHFP(dnslib.SSHFP, RD):
    @classmethod
    def create(
        cls, name: str, algorithm: int, fptype: int,
        fingerprint: str, ttl: int = 3600,
    ) -> DNSRecord:
        return DNSRecord(
            name=name,
            type=RecordType.SSHFP,
            data=cls(algorithm, fptype, fingerprint),
            ttl=ttl,
        )


__all__ = (
    "AAAA",
    "CAA",
    "CNAME",
    "DNAME",
    "DNSKEY",
    "DS",
    "HTTPS",
    "LOC",
    "MX",
    "NAPTR",
    "NS",
    "NSEC",
    "PTR",
    "RD",
    "RP",
    "RRSIG",
    "SOA",
    "SRV",
    "SSHFP",
    "TLSA",
    "TXT",
    "A",
    "DNSRecord",
    "DNSClass",
    "RecordType",
)
