from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from aiomisc.service.carbon import PROTOCOLS, CarbonSender, strip_carbon_ns


class TestStripCarbonNs:
    def test_basic_string(self):
        assert strip_carbon_ns("hello") == "hello"

    def test_with_special_chars(self):
        assert strip_carbon_ns("hello.world") == "hello_world"
        assert strip_carbon_ns("hello/world") == "hello_world"
        assert strip_carbon_ns("hello@world") == "hello_world"

    def test_with_leading_trailing_special(self):
        assert strip_carbon_ns(".hello.") == "hello"
        assert strip_carbon_ns("...hello...") == "hello"

    def test_uppercase_to_lowercase(self):
        assert strip_carbon_ns("HELLO") == "hello"
        assert strip_carbon_ns("Hello_World") == "hello_world"

    def test_with_numbers(self):
        assert strip_carbon_ns("hello123") == "hello123"
        assert strip_carbon_ns("123hello") == "123hello"

    def test_with_hyphen(self):
        assert strip_carbon_ns("hello-world") == "hello-world"

    def test_complex_string(self):
        result = strip_carbon_ns("Hello.World@123/Test")
        assert result == "hello_world_123_test"


class TestProtocols:
    def test_protocols_dict(self):
        assert "udp" in PROTOCOLS
        assert "tcp" in PROTOCOLS
        assert "pickle" in PROTOCOLS


class TestCarbonSender:
    def test_init_defaults(self):
        sender = CarbonSender()
        assert sender.host == "127.0.0.1"
        assert sender.port == 2003
        assert sender.send_interval == 5
        assert sender.protocol == "udp"
        assert sender.namespace == ("",)
        assert sender.name == "carbon-sender"

    def test_protocols_available(self):
        # Just test that the protocols dictionary is properly set up
        assert "udp" in PROTOCOLS
        assert "tcp" in PROTOCOLS
        assert "pickle" in PROTOCOLS
