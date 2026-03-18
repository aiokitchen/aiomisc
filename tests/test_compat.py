import asyncio
import os
import socket
from unittest.mock import MagicMock, patch

import pytest

from aiomisc.compat import (
    EventLoopMixin,
    Runner,
    default_loop_factory,
    entry_pont_iterator,
    sock_set_nodelay,
    sock_set_reuseport,
)


class TestEntryPointIterator:
    def test_entry_point_iterator_empty(self):
        # Test with a non-existent entry point group
        result = list(entry_pont_iterator("non_existent_group_xyz"))
        # May or may not be empty depending on installed packages
        assert isinstance(result, list)

    def test_entry_point_iterator_console_scripts(self):
        # Test with a common entry point group
        result = list(entry_pont_iterator("console_scripts"))
        assert isinstance(result, list)
        # All items should have name and load attributes
        for ep in result:
            assert hasattr(ep, "name")
            assert hasattr(ep, "load")


class TestEventLoopMixin:
    def test_loop_property_gets_running_loop(self):
        class MyClass(EventLoopMixin):
            pass

        async def test_coro():
            obj = MyClass()
            loop = obj.loop
            assert loop is asyncio.get_running_loop()

        asyncio.run(test_coro())

    def test_loop_property_caches_loop(self):
        class MyClass(EventLoopMixin):
            pass

        async def test_coro():
            obj = MyClass()
            loop1 = obj.loop
            loop2 = obj.loop
            assert loop1 is loop2

        asyncio.run(test_coro())


class TestDefaultLoopFactory:
    def test_default_loop_factory_without_uvloop(self):
        with patch("aiomisc.compat._uvloop_module", None):
            loop = default_loop_factory()
            try:
                assert isinstance(loop, asyncio.AbstractEventLoop)
            finally:
                loop.close()

    def test_default_loop_factory_with_uvloop(self):
        mock_uvloop = MagicMock()
        mock_loop = MagicMock(spec=asyncio.AbstractEventLoop)
        mock_uvloop.new_event_loop.return_value = mock_loop

        with patch("aiomisc.compat._uvloop_module", mock_uvloop):
            result = default_loop_factory()
            mock_uvloop.new_event_loop.assert_called_once()
            assert result is mock_loop


class TestRunner:
    def test_runner_is_asyncio_runner(self):
        assert Runner is asyncio.Runner


class TestSockSetNodelay:
    @pytest.mark.skipif(
        not hasattr(socket, "TCP_NODELAY"), reason="TCP_NODELAY not available"
    )
    def test_sock_set_nodelay_tcp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Should not raise - function handles the socket correctly
            result = sock_set_nodelay(sock)
            # Result is None for both cases
            assert result is None
        finally:
            sock.close()

    def test_sock_set_nodelay_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # Should not raise and should do nothing for UDP
            result = sock_set_nodelay(sock)
            assert result is None
        finally:
            sock.close()


class TestSockSetReuseport:
    @pytest.mark.skipif(
        not hasattr(socket, "SO_REUSEPORT"), reason="SO_REUSEPORT not available"
    )
    def test_sock_set_reuseport_enabled(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock_set_reuseport(sock, True)
            value = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)
            assert value != 0
        finally:
            sock.close()

    @pytest.mark.skipif(
        not hasattr(socket, "SO_REUSEPORT"), reason="SO_REUSEPORT not available"
    )
    def test_sock_set_reuseport_disabled(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock_set_reuseport(sock, False)
            value = sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)
            assert value == 0
        finally:
            sock.close()
