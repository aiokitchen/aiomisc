import os
import ssl
from pathlib import Path

import pytest

import aiomisc


def thread_pool_executor(request):
    return aiomisc.ThreadPoolExecutor


@pytest.fixture()
def certs():
    return Path(os.path.dirname(os.path.abspath(__file__))) / "certs"


@pytest.fixture
def ssl_client_context(certs):
    ca = str(certs / "ca.pem")
    key = str(certs / "client.key")
    cert = str(certs / "client.pem")

    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, capath=ca)

    if key:
        context.load_cert_chain(cert, key)

    context.load_verify_locations(cafile=ca)
    context.check_hostname = False
    context.verify_mode = ssl.VerifyMode.CERT_NONE

    return context
