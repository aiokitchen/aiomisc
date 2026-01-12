import asyncio
import os
import ssl
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

import aiomisc

try:
    import uvloop
except ImportError:
    uvloop = None  # type: ignore


@pytest.fixture
def timer():
    @contextmanager
    def timer(expected_time=0, *, dispersion=0.5):
        expected_time = float(expected_time)
        dispersion_value = expected_time * dispersion

        now = time.time()

        yield

        delta = time.time() - now

        lower_bound = expected_time - dispersion_value
        upper_bound = expected_time + dispersion_value

        assert lower_bound < delta < upper_bound

    return timer


def thread_pool_executor(request):
    return aiomisc.ThreadPoolExecutor


policies = (asyncio.DefaultEventLoopPolicy(),)
policy_ids = ("asyncio",)

if uvloop:
    policies = (uvloop.EventLoopPolicy(),) + policies  # type: ignore
    policy_ids = ("uvloop",) + policy_ids  # type: ignore


@pytest.fixture(params=policies, ids=policy_ids)
def event_loop_policy(request):
    return request.param


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
