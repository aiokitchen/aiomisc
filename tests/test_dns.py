import dnslib  # type: ignore[import-untyped]
import pytest

from aiomisc.service.dns import DNSStore, DNSZone
from aiomisc.service.dns.records import (
    AAAA,
    CAA,
    CNAME,
    DNSKEY,
    DS,
    HTTPS,
    LOC,
    MX,
    NAPTR,
    NS,
    NSEC,
    PTR,
    RP,
    RRSIG,
    SOA,
    SRV,
    SSHFP,
    TLSA,
    TXT,
    A,
    RecordType,
)
from aiomisc.service.dns.tree import RadixTree


def test_insert_and_search():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    assert tree.search(("com", "example")) == "Zone1"
    assert tree.search(("com", "example", "sub")) is None


def test_insert_multiple_and_search():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    tree.insert(("com", "example", "sub"), "Zone2")
    assert tree.search(("com", "example")) == "Zone1"
    assert tree.search(("com", "example", "sub")) == "Zone2"
    assert tree.search(("com", "example", "sub", "test")) is None


def test_find_prefix_basic():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    assert tree.find_prefix(("com", "example")) == (("com", "example"), "Zone1")
    assert tree.find_prefix(("com", "example", "sub")) == (
        ("com", "example"),
        "Zone1",
    )


def test_find_prefix_with_subdomain():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    tree.insert(("com", "example", "sub"), "Zone2")
    assert tree.find_prefix(("com", "example", "sub", "test")) == (
        ("com", "example", "sub"),
        "Zone2",
    )
    assert tree.find_prefix(("com", "example", "other")) == (
        ("com", "example"),
        "Zone1",
    )


def test_find_prefix_no_match():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    assert tree.find_prefix(("org", "example")) is None
    assert tree.find_prefix(("com", "nonexistent")) is None


def test_insert_and_override():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    tree.insert(("com", "example"), "Zone2")
    assert tree.search(("com", "example")) == "Zone2"


def test_deep_insert_and_search():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example", "sub", "deep", "deeper"), "Zone1")
    assert tree.search(("com", "example", "sub", "deep", "deeper")) == "Zone1"
    assert tree.search(("com", "example", "sub", "deep")) is None


def test_find_prefix_with_partial_matches():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("com", "example"), "Zone1")
    tree.insert(("com", "example", "sub"), "Zone2")
    tree.insert(("com", "example", "sub", "subsub"), "Zone3")
    assert tree.find_prefix(("com", "example", "sub", "subsub", "deep")) == (
        ("com", "example", "sub", "subsub"),
        "Zone3",
    )
    assert tree.find_prefix(("com", "example", "sub", "other")) == (
        ("com", "example", "sub"),
        "Zone2",
    )


def test_edge_cases_empty_key():
    tree: RadixTree[str] = RadixTree()
    tree.insert((), "RootZone")
    assert tree.search(()) == "RootZone"
    assert tree.find_prefix(("any", "key")) == ((), "RootZone")


def test_edge_cases_single_character_keys():
    tree: RadixTree[str] = RadixTree()
    tree.insert(("a",), "ZoneA")
    tree.insert(("b",), "ZoneB")
    assert tree.search(("a",)) == "ZoneA"
    assert tree.search(("b",)) == "ZoneB"
    assert tree.search(("c",)) is None
    assert tree.find_prefix(("a", "key")) == (("a",), "ZoneA")


def test_edge_cases_long_keys():
    tree: RadixTree[str] = RadixTree()
    long_key = tuple(str(i) for i in range(1000))
    tree.insert(long_key, "LongZone")
    assert tree.search(long_key) == "LongZone"
    assert tree.find_prefix(long_key + ("extra",)) == (
        tuple(long_key),
        "LongZone",
    )


@pytest.fixture
def dns_store():
    return DNSStore()


def test_add_zone(dns_store):
    zone = DNSZone("example.com.")
    dns_store.add_zone(zone)
    assert dns_store.get_zone("example.com.") is zone


def test_remove_zone(dns_store):
    zone = DNSZone("example.com.")
    dns_store.add_zone(zone)
    dns_store.remove_zone("example.com.")
    assert dns_store.get_zone("example.com.") is None


def test_add_record_to_zone(dns_store):
    zone = DNSZone("example.com.")
    record = A.create(name="www.example.com.", ip="192.0.2.1")
    zone.add_record(record)
    dns_store.add_zone(zone)
    records = dns_store.query("www.example.com.", RecordType.A)
    assert record in records


def test_query_nonexistent_record(dns_store):
    zone = DNSZone("example.com.")
    record = A.create(name="www.example.com.", ip="192.0.2.1")
    zone.add_record(record)
    dns_store.add_zone(zone)
    records = dns_store.query("nonexistent.example.com.", RecordType.A)
    assert len(records) == 0


def test_add_zone_with_existing_name(dns_store):
    zone = DNSZone("example.com.")
    dns_store.add_zone(zone)
    with pytest.raises(ValueError):
        dns_store.add_zone(zone)


def test_remove_nonexistent_zone(dns_store):
    with pytest.raises(ValueError):
        dns_store.remove_zone("nonexistent.com.")


def test_query_with_subdomain(dns_store):
    zone = DNSZone("example.com.")
    record = A.create(name="sub.example.com.", ip="192.0.2.2")
    zone.add_record(record)
    dns_store.add_zone(zone)
    records = dns_store.query("sub.example.com.", RecordType.A)
    assert record in records


def test_get_zone(dns_store):
    zone = DNSZone("example.com.")
    dns_store.add_zone(zone)
    assert dns_store.get_zone("example.com.") is zone


def test_get_nonexistent_zone(dns_store):
    assert dns_store.get_zone("nonexistent.com.") is None


def test_remove_record_from_zone(dns_store):
    zone = DNSZone("example.com.")
    record = A.create(name="www.example.com.", ip="192.0.2.1")
    zone.add_record(record)
    zone.remove_record(record)
    dns_store.add_zone(zone)
    records = dns_store.query("www.example.com.", RecordType.A)
    assert len(records) == 0


def test_find_prefix(dns_store):
    zone = DNSZone("example.com.")
    dns_store.add_zone(zone)
    assert dns_store.get_zone_for_name("sub.example.com.") == ("com", "example")


def test_a_create():
    record = A.create(name="example.com.", ip="192.0.2.1", ttl=300)
    assert record.name == "example.com."
    assert record.type == RecordType.A
    assert isinstance(record.data, dnslib.A)
    assert record.data.data == tuple(map(int, "192.0.2.1".split(".")))
    assert record.ttl == 300


def test_aaaa_create():
    record = AAAA.create(name="example.com.", ipv6="2001:db8::1", ttl=300)
    assert record.name == "example.com."
    assert record.type == RecordType.AAAA
    assert isinstance(record.data, dnslib.AAAA)
    assert record.data.data == (
        32,
        1,
        13,
        184,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        0,
        1,
    )
    assert record.ttl == 300


def test_cname_create():
    record = CNAME.create(
        name="example.com.", label="alias.example.com.", ttl=300
    )
    assert record.name == "example.com."
    assert record.type == RecordType.CNAME
    assert isinstance(record.data, dnslib.CNAME)
    assert record.data.label == "alias.example.com."
    assert record.ttl == 300


def test_mx_create():
    record = MX.create(
        name="example.com.",
        exchange="mail.example.com.",
        preference=10,
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.MX
    assert isinstance(record.data, dnslib.MX)
    assert record.data.label == "mail.example.com."
    assert record.data.preference == 10
    assert record.ttl == 300


def test_txt_create():
    record = TXT.create(name="example.com.", text="some text", ttl=300)
    assert record.name == "example.com."
    assert record.type == RecordType.TXT
    assert isinstance(record.data, dnslib.TXT)
    assert record.data.data == [b"some text"]
    assert record.ttl == 300


def test_soa_create():
    record = SOA.create(
        name="example.com.",
        mname="ns1.example.com.",
        rname="hostmaster.example.com.",
        serial=1,
        refresh=3600,
        retry=1800,
        expire=1209600,
        minimum=600,
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.SOA
    assert isinstance(record.data, dnslib.SOA)
    assert record.data.mname == "ns1.example.com."
    assert record.data.rname == "hostmaster.example.com."
    assert record.data.times == (1, 3600, 1800, 1209600, 600)
    assert record.ttl == 300


def test_ns_create():
    record = NS.create(name="example.com.", label="ns1.example.com.", ttl=300)
    assert record.name == "example.com."
    assert record.type == RecordType.NS
    assert isinstance(record.data, dnslib.NS)
    assert record.data.label == "ns1.example.com."
    assert record.ttl == 300


def test_ptr_create():
    record = PTR.create(
        name="1.2.3.4.in-addr.arpa.", label="example.com.", ttl=300
    )
    assert record.name == "1.2.3.4.in-addr.arpa."
    assert record.type == RecordType.PTR
    assert isinstance(record.data, dnslib.PTR)
    assert record.data.label == "example.com."
    assert record.ttl == 300


def test_srv_create():
    record = SRV.create(
        name="example.com.",
        priority=10,
        weight=20,
        port=80,
        target="target.example.com.",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.SRV
    assert isinstance(record.data, dnslib.SRV)
    assert record.data.priority == 10
    assert record.data.weight == 20
    assert record.data.port == 80
    assert record.data.target == "target.example.com."
    assert record.ttl == 300


def test_caa_create():
    record = CAA.create(
        name="example.com.",
        flags=0,
        tag="issue",
        value="letsencrypt.org",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.CAA
    assert isinstance(record.data, dnslib.CAA)
    assert record.data.flags == 0
    assert record.data.tag == "issue"
    assert record.data.value == "letsencrypt.org"
    assert record.ttl == 300


def test_naptr_create():
    record = NAPTR.create(
        name="example.com.",
        order=100,
        preference=10,
        flags="S",
        service="SIP+D2U",
        regexp="",
        replacement=".",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.NAPTR
    assert isinstance(record.data, dnslib.NAPTR)
    assert record.data.order == 100
    assert record.data.preference == 10
    assert record.data.flags == "S"
    assert record.data.service == "SIP+D2U"
    assert record.data.regexp == ""
    assert record.data.replacement == "."
    assert record.ttl == 300


def test_ds_create():
    record = DS.create(
        name="example.com.",
        key_tag=12345,
        algorithm=5,
        digest_type=1,
        digest="abc123",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.DS
    assert isinstance(record.data, dnslib.DS)
    assert record.data.key_tag == 12345
    assert record.data.algorithm == 5
    assert record.data.digest_type == 1
    assert record.data.digest == b"abc123"
    assert record.ttl == 300


def test_dnskey_create():
    record = DNSKEY.create(
        name="example.com.",
        flags=256,
        protocol=3,
        algorithm=5,
        key="abcdefg",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.DNSKEY
    assert isinstance(record.data, dnslib.DNSKEY)
    assert record.data.flags == 256
    assert record.data.protocol == 3
    assert record.data.algorithm == 5
    assert record.data.key == b"abcdefg"
    assert record.ttl == 300


def test_rrsig_create():
    record = RRSIG.create(
        name="example.com.",
        type_covered=RecordType.A,
        algorithm=5,
        labels=2,
        original_ttl=300,
        expiration=1234567890,
        inception=1234560000,
        key_tag=12345,
        signer="example.com.",
        signature="abcdefg",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.RRSIG
    assert isinstance(record.data, dnslib.RRSIG)
    assert record.data.covered == RecordType.A
    assert record.data.algorithm == 5
    assert record.data.labels == 2
    assert record.data.orig_ttl == 300
    assert record.data.sig_exp == 1234567890
    assert record.data.sig_inc == 1234560000
    assert record.data.key_tag == 12345
    assert record.data.name == "example.com."
    assert record.data.sig == "abcdefg"
    assert record.ttl == 300


def test_nsec_create():
    record = NSEC.create(
        name="example.com.",
        next_domain="next.example.com.",
        rrtypes=[RecordType.A, RecordType.AAAA],
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.NSEC
    assert isinstance(record.data, dnslib.NSEC)
    assert record.data.label == "next.example.com."
    assert record.data.rrlist == [RecordType.A, RecordType.AAAA]
    assert record.ttl == 300


def test_https_create():
    record = HTTPS.create(
        name="example.com.",
        priority=10,
        target="target.example.com.",
        params=["param1", "param2"],
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.HTTPS
    assert isinstance(record.data, dnslib.HTTPS)
    assert record.data.priority == 10
    assert record.data.target == "target.example.com."
    assert record.data.params == ["param1", "param2"]
    assert record.ttl == 300


def test_loc_create():
    record = LOC.create(
        name="example.com.",
        latitude=12.34,
        longitude=56.78,
        altitude=90.0,
        size=1.0,
        h_precision=2.0,
        v_precision=3.0,
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.LOC
    assert isinstance(record.data, dnslib.LOC)
    assert record.data.lat == "12 20 24.000 N"
    assert record.data.lon == "56 46 48.000 E"
    assert record.data.alt == 90.0
    assert record.data.siz == 1.0
    assert record.data.hp == 2.0
    assert record.data.vp == 3.0
    assert record.ttl == 300


def test_rp_create():
    record = RP.create(
        name="example.com.",
        mbox="hostmaster.example.com.",
        txt="contact.example.com.",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.RP
    assert isinstance(record.data, dnslib.RP)
    assert record.data.mbox == "hostmaster.example.com."
    assert record.data.txt == "contact.example.com."
    assert record.ttl == 300


def test_tlsa_create():
    record = TLSA.create(
        name="example.com.",
        usage=1,
        selector=1,
        mtype=1,
        cert="abcdefg",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.TLSA
    assert isinstance(record.data, dnslib.TLSA)
    assert record.data.cert_usage == 1
    assert record.data.selector == 1
    assert record.data.matching_type == 1
    assert record.data.cert_data == b"abcdefg"
    assert record.ttl == 300


def test_sshfp_create():
    record = SSHFP.create(
        name="example.com.",
        algorithm=1,
        fptype=1,
        fingerprint="abcdefg",
        ttl=300,
    )
    assert record.name == "example.com."
    assert record.type == RecordType.SSHFP
    assert isinstance(record.data, dnslib.SSHFP)
    assert record.data.algorithm == 1
    assert record.data.fp_type == 1
    assert record.data.fingerprint == b"abcdefg"
    assert record.ttl == 300


def test_zone_replace(dns_store):
    zone = DNSZone("example.com.")
    record1 = A.create(name="www.example.com.", ip="192.0.2.1")
    record2 = A.create(name="api.example.com.", ip="192.0.2.2")
    zone.add_record(record1)
    dns_store.add_zone(zone)

    zone.replace([record2])

    records = dns_store.query("www.example.com.", RecordType.A)
    assert len(records) == 0
    records = dns_store.query("api.example.com.", RecordType.A)
    assert len(records) == 1
    assert record2 in records


def test_zone_replace_multiple_records():
    zone = DNSZone("example.com.")
    record1 = A.create(name="www.example.com.", ip="192.0.2.1")
    record2 = A.create(name="www.example.com.", ip="192.0.2.2")

    zone.replace([record1, record2])
    records = zone.get_records("www.example.com.", RecordType.A)
    assert len(records) == 2
    assert record1 in records
    assert record2 in records


def test_zone_replace_empty():
    zone = DNSZone("example.com.")
    record = A.create(name="www.example.com.", ip="192.0.2.1")
    zone.add_record(record)

    zone.replace([])
    records = zone.get_records("www.example.com.", RecordType.A)
    assert len(records) == 0


def test_zone_replace_invalid_record():
    zone = DNSZone("example.com.")
    record = A.create(name="www.other.com.", ip="192.0.2.1")

    with pytest.raises(ValueError, match="does not belong to zone"):
        zone.replace([record])


def test_store_replace_basic(dns_store):
    zone1 = DNSZone("example.com.")
    record1 = A.create(name="www.example.com.", ip="192.0.2.1")
    zone1.add_record(record1)
    dns_store.add_zone(zone1)

    zone2 = DNSZone("test.com.")
    record2 = A.create(name="www.test.com.", ip="192.0.2.2")
    zone2.add_record(record2)
    dns_store.add_zone(zone2)

    # Replace with new data
    new_record1 = A.create(name="api.example.com.", ip="192.0.2.3")
    new_record2 = A.create(name="api.test.com.", ip="192.0.2.4")

    dns_store.replace(
        {"example.com.": [new_record1], "test.com.": [new_record2]}
    )

    # Check old records are gone
    records = dns_store.query("www.example.com.", RecordType.A)
    assert len(records) == 0
    records = dns_store.query("www.test.com.", RecordType.A)
    assert len(records) == 0

    # Check new records are present
    records = dns_store.query("api.example.com.", RecordType.A)
    assert len(records) == 1
    assert new_record1 in records
    records = dns_store.query("api.test.com.", RecordType.A)
    assert len(records) == 1
    assert new_record2 in records


def test_store_replace_empty(dns_store):
    zone = DNSZone("example.com.")
    record = A.create(name="www.example.com.", ip="192.0.2.1")
    zone.add_record(record)
    dns_store.add_zone(zone)

    dns_store.replace({})

    assert dns_store.get_zone("example.com.") is None
    records = dns_store.query("www.example.com.", RecordType.A)
    assert len(records) == 0


def test_store_replace_multiple_records_per_zone(dns_store):
    new_record1 = A.create(name="www.example.com.", ip="192.0.2.1")
    new_record2 = A.create(name="www.example.com.", ip="192.0.2.2")

    dns_store.replace({"example.com.": [new_record1, new_record2]})

    records = dns_store.query("www.example.com.", RecordType.A)
    assert len(records) == 2
    assert new_record1 in records
    assert new_record2 in records
