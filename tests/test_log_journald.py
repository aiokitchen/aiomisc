import logging
import os
import platform
import struct
from collections import deque
from io import BytesIO
from pathlib import Path
from socket import AF_UNIX, SOCK_DGRAM
from tempfile import TemporaryDirectory

import pytest

import aiomisc
from aiomisc import bind_socket, threaded
from aiomisc.service import UDPServer
from aiomisc_log.formatter.journald import JournaldLogHandler


pytestmark = pytest.mark.skipif(
    platform.system() == "Windows",
    reason="Unix only tests",
)


def test_journald_logger(loop, subtests):
    with TemporaryDirectory(dir="/tmp") as tmp_dir:
        tmp_path = Path(tmp_dir)
        sock_path = tmp_path / "notify.sock"

        logs = deque()

        class FakeJournald(UDPServer):
            VALUE_LEN_STRUCT = struct.Struct("<Q")

            def handle_datagram(self, data: bytes, addr: tuple) -> None:
                result = {}
                with BytesIO(data) as fp:
                    line = fp.readline()
                    while line:
                        if b"=" not in line:
                            key = line.decode().strip()
                            value_len = self.VALUE_LEN_STRUCT.unpack(
                                fp.read(
                                    self.VALUE_LEN_STRUCT.size,
                                ),
                            )[0]
                            value = fp.read(value_len).decode()
                            assert fp.read(1) == b"\n"
                        else:
                            key, value = map(
                                lambda x: x.strip(),
                                line.decode().split("=", 1),
                            )

                        result[key] = value
                        line = fp.readline()

                logs.append(result)

        @threaded
        def log_writer():
            log = logging.getLogger("test")
            log.propagate = False
            log.handlers.clear()
            log.handlers.append(JournaldLogHandler())

            log.info("Test message")
            log.info("Test multiline\nmessage")
            log.info(
                "Test formatted: int=%d str=%s repr=%r float=%0.1f",
                1, 2, 3, 4,
            )

            log.info(
                "Message with extra", extra={
                    "foo": "bar",
                },
            )

            try:
                1 / 0
            except ZeroDivisionError:
                log.exception("Sample exception")

        with bind_socket(AF_UNIX, SOCK_DGRAM, address=str(sock_path)) as sock:
            JournaldLogHandler.SOCKET_PATH = sock_path

            with aiomisc.entrypoint(FakeJournald(sock=sock), loop=loop):
                loop.run_until_complete(log_writer())

    assert len(logs) == 5

    required_fields = {
        "MESSAGE", "MESSAGE_ID", "MESSAGE_RAW", "PRIORITY",
        "SYSLOG_FACILITY", "CODE", "CODE_FUNC", "CODE_FILE",
        "CODE_LINE", "CODE_MODULE", "LOGGER_NAME", "PID",
        "PROCESS_NAME", "THREAD_ID", "THREAD_NAME",
        "RELATIVE_USEC", "CREATED_USEC",
    }

    with subtests.test("simple message"):
        message = logs.popleft()
        assert message["MESSAGE"] == "Test message"
        assert message["MESSAGE_RAW"] == "Test message"
        assert message["PRIORITY"] == "6"
        assert message["CODE_FUNC"] == "log_writer"
        assert int(message["PID"]) == os.getpid()
        for field in required_fields:
            assert field in message

    with subtests.test("multiline message"):
        message = logs.popleft()
        assert message["MESSAGE"] == "Test multiline\nmessage"
        assert message["MESSAGE_RAW"] == "Test multiline\nmessage"
        assert message["PRIORITY"] == "6"
        assert message["CODE_FUNC"] == "log_writer"
        assert int(message["PID"]) == os.getpid()

        for field in required_fields:
            assert field in message

    with subtests.test("formatted message"):
        message = logs.popleft()
        assert message["MESSAGE"] == (
            "Test formatted: int=1 str=2 repr=3 float=4.0"
        )
        assert message["MESSAGE_RAW"] == (
            "Test formatted: int=%d str=%s repr=%r float=%0.1f"
        )
        assert message["ARGUMENTS_0"] == "1"
        assert message["ARGUMENTS_1"] == "2"
        assert message["ARGUMENTS_2"] == "3"
        assert message["ARGUMENTS_3"] == "4"
        assert message["PRIORITY"] == "6"
        assert message["CODE_FUNC"] == "log_writer"
        assert int(message["PID"]) == os.getpid()

        for field in required_fields:
            assert field in message

    with subtests.test("message with extra"):
        message = logs.popleft()
        assert message["MESSAGE"] == "Message with extra"
        assert message["MESSAGE_RAW"] == "Message with extra"
        assert message["PRIORITY"] == "6"
        assert message["CODE_FUNC"] == "log_writer"
        assert message["EXTRA_FOO"] == "bar"
        assert int(message["PID"]) == os.getpid()

        for field in required_fields:
            assert field in message

    with subtests.test("exception message"):
        message = logs.popleft()
        assert message["MESSAGE"].startswith("Sample exception\nTraceback")
        assert message["MESSAGE_RAW"] == "Sample exception"
        assert message["PRIORITY"] == "3"
        assert message["CODE_FUNC"] == "log_writer"
        assert int(message["PID"]) == os.getpid()
        assert message["EXCEPTION_TYPE"] == "<class 'ZeroDivisionError'>"
        assert message["EXCEPTION_VALUE"] == "division by zero"
        assert message["TRACEBACK"].startswith(
            "Traceback (most recent call last)",
        )

        for field in required_fields:
            assert field in message
