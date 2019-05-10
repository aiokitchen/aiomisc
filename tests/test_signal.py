import asyncio

import pytest

from aiomisc import entrypoint, Service, Signal


class FooService(Service):

    async def start(self):
        ...


def test_pre_start_signal(loop):
    expected_services = tuple(FooService() for _ in range(2))
    ep = entrypoint(*expected_services, loop=loop)
    received_services = None

    async def pre_start_callback(services, sender=None):
        nonlocal received_services
        received_services = services

    ep.pre_start.connect(pre_start_callback)

    with ep:
        assert received_services == expected_services


def test_post_stop_signal(loop):
    ep = entrypoint(FooService(), loop=loop)
    called = False

    async def post_stop_callback(sender=None):
        nonlocal called
        await asyncio.sleep(0.01)
        called = True

    ep.post_stop.connect(post_stop_callback)

    with ep:
        assert not called

    assert called


def test_connect_to_frozen_signal():

    async def cb(sender=None):
        ...

    signal = Signal()
    signal.freeze()

    with pytest.raises(RuntimeError):
        signal.connect(cb)


@pytest.mark.parametrize('callback', [
    None,
    max,
    lambda x: x
])
def test_wrong_callback(callback):
    signal = Signal()

    with pytest.raises(RuntimeError):
        signal.connect(callback)
