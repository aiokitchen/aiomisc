import asyncio
import concurrent.futures
import os
import ssl
import uvloop
from contextlib import contextmanager
from pathlib import Path

import pytest
import time

import aiomisc


@pytest.fixture
def timer():
    @contextmanager
    def timer(expected_time=0, *, dispersion=0.5):
        expected_time = float(expected_time)
        dispersion_value = expected_time * dispersion

        now = time.monotonic()

        yield

        delta = time.monotonic() - now

        lower_bound = expected_time - dispersion_value
        upper_bound = expected_time + dispersion_value

        assert lower_bound < delta < upper_bound

    return timer


thread_pool_implementation = (
    aiomisc.ThreadPoolExecutor,
    concurrent.futures.ThreadPoolExecutor,
)


thread_pool_ids = (
    'aiomisc pool',
    'default pool',
)


@pytest.fixture(params=thread_pool_implementation, ids=thread_pool_ids)
def thread_pool_executor(request):
    return request.param


policies = (
    uvloop.EventLoopPolicy(),
    asyncio.DefaultEventLoopPolicy(),
)

policy_ids = (
    'uvloop',
    'asyncio',
)


@pytest.fixture(params=policies, ids=policy_ids)
def event_loop_policy(request):
    return request.param


@pytest.fixture()
def certs():
    return Path(os.path.dirname(os.path.abspath(__file__))) / 'certs'


@pytest.fixture(params=(ssl.Purpose.SERVER_AUTH, ssl.Purpose.CLIENT_AUTH))
def ssl_client_context(request, certs):
    ca = str(certs / 'ca.pem')
    key = str(certs / 'client.key')
    cert = str(certs / 'client.pem')

    context = ssl.create_default_context(request.param, capath=ca)

    if key:
        context.load_cert_chain(
            cert,
            key,
        )

    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    return context
