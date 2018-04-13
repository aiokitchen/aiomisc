import json
import logging
import socket
import time
import uuid

import pytest

from aiomisc.utils import chunk_list, bind_socket
from aiomisc.log import basic_config


def test_chunk_list(event_loop):
    data = tuple(map(tuple, chunk_list(range(10), 3)))

    assert data == ((0, 1, 2), (3, 4, 5), (6, 7, 8), (9,))


def test_configure_logging_json(capsys):
    data = str(uuid.uuid4())

    basic_config(level=logging.DEBUG, log_format='json', buffered=False)
    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    json_result = json.loads(stdout.strip())
    assert json_result['msg'] == data

    logging.basicConfig(handlers=[], level=logging.INFO)


def test_configure_logging_stderr(capsys):
    data = str(uuid.uuid4())

    out, err = capsys.readouterr()

    # logging.basicConfig(level=logging.INFO)
    basic_config(level=logging.DEBUG, log_format='stream', buffered=False)

    logging.info(data)

    time.sleep(0.3)
    stdout, stderr = capsys.readouterr()

    assert data in stderr

    logging.basicConfig(handlers=[])


@pytest.mark.parametrize("address,family", [
    ("127.0.0.1", socket.AF_INET),
    ("0.0.0.0", socket.AF_INET),
    ("::1", socket.AF_INET6),
    ("::", socket.AF_INET6),
])
def test_bind_address(address, family, unused_tcp_port):
    sock = bind_socket(address=address, port=unused_tcp_port)

    assert isinstance(sock, socket.socket)
    assert sock.family == family
