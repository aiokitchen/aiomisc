import asyncio

import pytest

import aiomisc
from aiomisc import Service, Signal, entrypoint, receiver


@pytest.fixture
def signal():
    return Signal()


@pytest.fixture(autouse=True, scope="module")
def clear_entrypoint_signals():
    entrypoint.PRE_START = Signal()
    entrypoint.POST_STOP = Signal()


class FooService(Service):
    async def start(self): ...


def test_pre_start_signal(event_loop):
    expected_services = frozenset(FooService() for _ in range(2))
    ep = entrypoint(*expected_services, loop=event_loop)
    received_services = None

    async def pre_start_callback(services, entrypoint):
        nonlocal received_services
        received_services = frozenset(services)

    ep.pre_start.connect(pre_start_callback)

    with ep:
        assert received_services == expected_services


def test_post_stop_signal(event_loop):
    ep = entrypoint(FooService(), loop=event_loop)
    called = False

    async def post_stop_callback(*_, **__):
        nonlocal called
        await asyncio.sleep(0.01)
        called = True

    ep.post_stop.connect(post_stop_callback)

    with ep:
        assert not called

    assert called


def test_entrypoint_class_pre_start_signal(event_loop):
    received_services, received_entrypoint = None, None

    async def pre_start_callback(*, services, entrypoint):
        nonlocal received_services, received_entrypoint
        received_services = services
        received_entrypoint = entrypoint

    entrypoint.PRE_START.connect(pre_start_callback)

    expected_services = (FooService(),)
    ep = entrypoint(*expected_services, loop=event_loop)
    with ep:
        assert received_services == expected_services
        assert received_entrypoint == ep


def test_entrypoint_class_post_stop_signal(event_loop):
    received_entrypoint = None

    async def post_stop_callback(*, services, entrypoint):
        nonlocal received_entrypoint
        received_entrypoint = entrypoint

    entrypoint.POST_STOP.connect(post_stop_callback)

    ep = entrypoint(FooService(), loop=event_loop)

    with ep:
        ...

    assert received_entrypoint == ep


def test_connect_to_frozen_signal(signal):
    signal.freeze()

    async def cb(): ...

    with pytest.raises(RuntimeError):
        signal.connect(cb)


@pytest.mark.parametrize("callback", [None, max, lambda x: x])
def test_wrong_callback(signal, callback):
    with pytest.raises(RuntimeError):
        signal.connect(callback)


async def test_receiver_decorator(signal):
    called = False

    @receiver(signal)
    async def foo():
        nonlocal called
        called = True

    await signal.call()
    assert called


async def test_call_arguments(signal):
    received_args, received_kwargs = None, None

    @receiver(signal)
    async def foo(*args, **kwargs):
        nonlocal received_args, received_kwargs
        received_args, received_kwargs = args, kwargs

    await signal.call("foo", "bar", spam="spam")
    assert received_args == ("foo", "bar")
    assert received_kwargs == {"spam": "spam"}


async def multiple_receivers(signal):
    foo_called = False
    bar_called = False

    @receiver(signal)
    async def foo():
        nonlocal foo_called
        foo_called = True

    @receiver(signal)
    async def bar():
        nonlocal bar_called
        bar_called = True

    await signal.call()

    assert all((foo_called, bar_called))


async def test_add_remove_service_with_signals(entrypoint: aiomisc.Entrypoint):
    all_services = list()

    async def pre_start_hook(*, entrypoint, services):
        for service in services:
            all_services.append(service)

    pre_start_services = list()

    class SimpleService(aiomisc.Service):
        async def start(self) -> None:
            nonlocal pre_start_services
            pre_start_services.append(self)

    entrypoint.pre_start = entrypoint.pre_start.copy()
    entrypoint.post_start = entrypoint.post_start.copy()

    entrypoint.pre_start.connect(pre_start_hook)
    entrypoint.post_start.connect(pre_start_hook)

    entrypoint.pre_start.freeze()
    entrypoint.post_start.freeze()

    service = SimpleService()

    await entrypoint.start_services(service)

    assert len(all_services) == 2
    assert all_services == [service, service]

    assert len(pre_start_services) == 1
    assert service in pre_start_services
