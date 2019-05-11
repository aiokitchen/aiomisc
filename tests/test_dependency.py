import asyncio

import pytest

from aiomisc import dependency, Service, entrypoint
from aiomisc.dependency import freeze, consumer, inject


async def test_register_dependency():

    @dependency
    async def foo():
        return 'Foo'

    @dependency
    async def spam(foo):
        return foo * 3

    freeze()

    @consumer
    async def consume(spam):
        return spam

    await consume() == 'FooFooFoo'


async def test_inject_dependencies():

    @dependency
    async def foo():
        return 'Foo'

    @dependency
    async def bar():
        return 'Bar'

    class Target:
        ...

    target = Target()

    await inject(target, ('foo', 'bar'))

    assert target.foo == 'Foo'
    assert target.bar == 'Bar'


def test_dependency_injection():

    @dependency
    async def foo():
        yield 'Foo'

    @dependency
    async def bar():
        yield 'Bar'

    class TestService(Service):
        __dependencies__ = ('foo', 'bar')

        async def start(self):
            ...

    service = TestService()

    with entrypoint(service):
        assert service.foo == 'Foo'
        assert service.bar == 'Bar'


def test_missed_dependency_exception():

    class TestService(Service):
        __dependencies__ = ('spam',)

        async def start(self):
            ...

    with pytest.raises(RuntimeError):
        with entrypoint(TestService()):
            ...


def test_graceful_dependency_shutdown():

    @dependency
    async def spam():
        resource = ['spam'] * 3
        yield resource
        resource.clear()

    class TestService(Service):
        __dependencies__ = ('spam',)

        async def start(self):
            ...

    service = TestService()

    resource = None
    with entrypoint(service):
        resource = service.spam
        assert resource == ['spam'] * 3

    assert resource == []


def test_set_dependency_in_init():

    @dependency
    async def answer():
        yield 777

    class TestService(Service):
        __dependencies__ = ('answer',)

        async def start(self):
            ...

    service = TestService(answer=42)

    with entrypoint(service):
        assert service.answer == 42


def test_coroutine_function_dependency():

    @dependency
    async def foo():
        await asyncio.sleep(0.1)
        return 'Foo'

    @dependency
    async def bar():
        return 'Bar'

    class TestService(Service):
        __dependencies__ = ('foo', 'bar',)

        async def start(self):
            ...

    service = TestService()

    with entrypoint(service):
        assert service.foo == 'Foo'
        assert service.bar == 'Bar'


def test_dependencies_for_depndencies():

    @dependency
    async def foo():
        return 'Foo'

    @dependency
    async def spam(foo):
        return foo * 3

    class TestService(Service):
        __dependencies__ = ('spam',)

        async def start(self):
            ...

    service = TestService()

    with entrypoint(service):
        assert service.spam == 'FooFooFoo'


def test_loop_dependency():
    injected_loop = None

    @dependency
    def need_loop(loop):
        nonlocal injected_loop
        injected_loop = loop

    with entrypoint() as loop:
        assert loop == injected_loop
