import asyncio
import hashlib
import hmac
import logging
import os
import signal
import socket
from types import TracebackType
from unittest.mock import MagicMock, patch

import pytest

from aiomisc_worker import INT_SIGNAL, PacketTypes, SIGNAL
from aiomisc_worker.protocol import ADDRESS_FAMILY, SocketIOProtocol
from aiomisc_worker.worker import (
    bad_initializer,
    execute,
    on_cancel_signal,
    on_exception,
)

from tests import unix_only


class TestOnCancelSignal:
    def test_raises_cancelled_error(self):
        with pytest.raises(asyncio.CancelledError):
            on_cancel_signal(None, None)


class TestOnException:
    def test_on_exception_with_none(self):
        # Should not raise when all args are None
        on_exception(None, None, None)

    def test_on_exception_logs_exception(self):
        with patch("logging.exception") as mock_log:
            try:
                raise ValueError("test error")
            except ValueError:
                import sys

                exc_info = sys.exc_info()
                on_exception(*exc_info)

            mock_log.assert_called_once()


class TestExecute:
    def test_execute_success(self):
        mock_proto = MagicMock(spec=SocketIOProtocol)

        def test_func(a, b):
            return a + b

        mock_proto.receive.return_value = (
            PacketTypes.REQUEST,
            test_func,
            (1, 2),
            {},
        )

        execute(mock_proto)

        mock_proto.send.assert_called_once()
        call_args = mock_proto.send.call_args[0][0]
        assert call_args[0] == PacketTypes.RESULT
        assert call_args[1] == 3

    def test_execute_with_exception(self):
        mock_proto = MagicMock(spec=SocketIOProtocol)

        def failing_func():
            raise ValueError("test error")

        mock_proto.receive.return_value = (
            PacketTypes.REQUEST,
            failing_func,
            (),
            {},
        )

        execute(mock_proto)

        mock_proto.send.assert_called_once()
        call_args = mock_proto.send.call_args[0][0]
        assert call_args[0] == PacketTypes.EXCEPTION
        assert isinstance(call_args[1], ValueError)

    def test_execute_connection_error(self):
        mock_proto = MagicMock(spec=SocketIOProtocol)
        mock_proto.receive.side_effect = ConnectionError("disconnected")

        with pytest.raises(ConnectionError):
            execute(mock_proto)

    def test_execute_wrong_packet_type(self):
        mock_proto = MagicMock(spec=SocketIOProtocol)
        mock_proto.receive.return_value = (
            PacketTypes.RESULT,  # Wrong packet type
            lambda: None,
            (),
            {},
        )

        with pytest.raises(RuntimeError, match="Unexpected request"):
            execute(mock_proto)


class TestBadInitializer:
    @unix_only
    def test_bad_initializer(self):
        # Create a mock server to receive the bad_initializer message
        server_sock = socket.socket(ADDRESS_FAMILY, socket.SOCK_STREAM)
        try:
            if ADDRESS_FAMILY == socket.AF_UNIX:
                import tempfile

                sock_path = tempfile.mktemp(suffix=".sock")
                server_sock.bind(sock_path)
            else:
                server_sock.bind(("", 0))
                sock_path = server_sock.getsockname()

            server_sock.listen(1)

            import threading

            received_data = []

            def server_handler():
                conn, _ = server_sock.accept()
                proto = SocketIOProtocol(conn)
                received_data.append(proto.receive())
                received_data.append(proto.receive())
                conn.close()

            server_thread = threading.Thread(target=server_handler)
            server_thread.start()

            # Call bad_initializer
            cookie = b"test_cookie"
            worker_id = b"worker_1"
            exc = ValueError("initializer failed")

            bad_initializer(sock_path, cookie, worker_id, exc)

            server_thread.join(timeout=5)

            # Verify the message format
            assert len(received_data) == 2
            auth_packet = received_data[0]
            assert auth_packet[0] == PacketTypes.BAD_INITIALIZER
            assert auth_packet[1] == worker_id

            exc_packet = received_data[1]
            assert exc_packet[0] == PacketTypes.EXCEPTION
            assert isinstance(exc_packet[1], ValueError)

        finally:
            server_sock.close()
            if ADDRESS_FAMILY == socket.AF_UNIX:
                try:
                    os.unlink(sock_path)
                except OSError:
                    pass


class TestSignalConstants:
    @unix_only
    def test_signal_is_sigusr2_on_unix(self):
        import platform

        if platform.system() != "Windows":
            assert SIGNAL == signal.SIGUSR2

    def test_int_signal_is_sigint(self):
        assert INT_SIGNAL == signal.SIGINT
