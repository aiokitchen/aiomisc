import socket

import dnslib  # type: ignore[import-untyped]
import pytest

from aiomisc import threaded
from aiomisc.service.dns import DNSStore, DNSZone, TCPDNSServer, UDPDNSServer
from aiomisc.service.dns.records import AAAA, CNAME, A, RecordType
from aiomisc.service.dns.service import TCP_HEADER_STRUCT


@pytest.fixture
def dns_store_filled():
    store = DNSStore()
    zone = DNSZone("example.com.")
    a_record = A.create(name="sub.example.com.", ip="192.0.2.1", ttl=3600)
    aaaa_record = AAAA.create(
        name="ipv6.example.com.", ipv6="2001:db8::1", ttl=3600
    )
    cname_record = CNAME.create(name="alias.example.com.", label="example.com.")
    zone.add_record(a_record)
    zone.add_record(aaaa_record)
    zone.add_record(cname_record)
    store.add_zone(zone)
    return store


@pytest.fixture
def dns_server_port(aiomisc_unused_port_factory) -> int:
    return aiomisc_unused_port_factory()


@pytest.fixture
def dns_server_udp(dns_store_filled: DNSStore, dns_server_port) -> UDPDNSServer:
    server = UDPDNSServer(
        store=dns_store_filled, address="localhost", port=dns_server_port
    )
    return server


@pytest.fixture
def dns_server_tcp(dns_store_filled: DNSStore, dns_server_port) -> TCPDNSServer:
    server = TCPDNSServer(
        store=dns_store_filled, address="localhost", port=dns_server_port
    )
    return server


@pytest.fixture
def services(dns_server_udp, dns_server_tcp):
    return [dns_server_udp, dns_server_tcp]


@threaded
def dns_send_receive_udp(data, port):
    # Send the query
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(5)
        sock.sendto(data, ("localhost", port))
        # Receive the response
        response_data, _ = sock.recvfrom(65535)
        return dnslib.DNSRecord.parse(response_data)


@threaded
def dns_send_receive_tcp(data, port):
    # Send the query
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(("localhost", port))
        sock.sendall(data)
        # Receive the response length (2 bytes)
        length_data = sock.recv(2)
        length = int.from_bytes(length_data, byteorder="big")
        # Receive the actual response
        response_data = sock.recv(length)
        return dnslib.DNSRecord.parse(response_data)


async def test_handle_datagram_a_record(services, dns_server_port):
    # Prepare a DNS query for A record
    query = dnslib.DNSRecord.question("sub.example.com.", qtype="A")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NOERROR
    assert len(response.rr) == 1
    assert str(response.rr[0].rname) == "sub.example.com."
    assert response.rr[0].rdata == dnslib.A("192.0.2.1")


async def test_handle_datagram_aaaa_record(services, dns_server_port):
    # Prepare a DNS query for AAAA record
    query = dnslib.DNSRecord.question("ipv6.example.com.", qtype="AAAA")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NOERROR
    assert len(response.rr) == 1
    assert str(response.rr[0].rname) == "ipv6.example.com."
    assert response.rr[0].rdata == dnslib.AAAA("2001:db8::1")


async def test_handle_datagram_cname_record(services, dns_server_port):
    # Prepare a DNS query for CNAME record
    query = dnslib.DNSRecord.question("alias.example.com.", qtype="CNAME")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NOERROR
    assert len(response.rr) == 1
    assert str(response.rr[0].rname) == "alias.example.com."
    assert response.rr[0].rdata == dnslib.CNAME("example.com.")


async def test_handle_datagram_nonexistent_record(services, dns_server_port):
    # Prepare a DNS query for a nonexistent record
    query = dnslib.DNSRecord.question("nonexistent.example.com.", qtype="A")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NXDOMAIN
    assert len(response.rr) == 0


async def test_handle_datagram_remove_record(
    services, dns_store_filled, dns_server_port
):
    # Remove an existing record from the zone
    zone = dns_store_filled.get_zone("example.com.")

    for record in zone.get_records("sub.example.com.", RecordType.A):
        zone.remove_record(record)

    # Prepare a DNS query for the removed record
    query = dnslib.DNSRecord.question("sub.example.com.", qtype="A")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NXDOMAIN
    assert len(response.rr) == 0


async def test_handle_datagram_edns_record(services, dns_server_port):
    # Prepare a DNS query with EDNS0
    query = dnslib.DNSRecord.question("sub.example.com.", qtype="A")
    query.add_ar(dnslib.EDNS0(udp_len=4096))
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response
    assert response.header.rcode == dnslib.RCODE.NOERROR
    assert len(response.rr) == 1
    assert str(response.rr[0].rname) == "sub.example.com."
    assert response.rr[0].rdata == dnslib.A("192.0.2.1")
    assert response.ar[0].rtype == dnslib.QTYPE.OPT


async def test_handle_large_datagram_truncated_udp(
    services, dns_server_port, dns_store_filled
):
    # Add many A records to the store to exceed typical UDP packet size
    zone = dns_store_filled.get_zone("example.com.")
    for i in range(1, 101):
        a_record = A.create(name="rr.example.com.", ip=f"192.0.2.{i}")
        zone.add_record(a_record)

    # Prepare a DNS query
    query = dnslib.DNSRecord.question("rr.example.com.", qtype="A")
    query_data = query.pack()

    response = await dns_send_receive_udp(query_data, dns_server_port)

    # Verify the response is truncated
    assert response.header.tc == 1  # Ensure the TC (truncated) bit is set


async def test_handle_large_tcp_request(
    services, dns_server_port, dns_store_filled
):
    # Add many A records to the store to exceed typical UDP packet size
    zone = dns_store_filled.get_zone("example.com.")
    for i in range(1, 101):
        a_record = A.create(name="rr.example.com.", ip=f"192.0.2.{i}", ttl=3600)
        zone.add_record(a_record)

    # Prepare a DNS query for TCP
    query = dnslib.DNSRecord.question("rr.example.com.", qtype="A")
    query_data = TCP_HEADER_STRUCT.pack(len(query.pack())) + query.pack()

    response = await dns_send_receive_tcp(query_data, dns_server_port)

    # Verify the TCP response is not truncated and contains all records
    assert response.header.rcode == dnslib.RCODE.NOERROR
    assert len(response.rr) == 100
    assert all(str(rr.rname).startswith("rr") for rr in response.rr)
