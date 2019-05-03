import pytest

from aiomisc import Service, dependency, entrypoint, DEPENDENCIES


pytestmark = pytest.mark.catch_loop_exceptions


@pytest.fixture(autouse=True)
def clear_dependencies():
    DEPENDENCIES.clear()
    yield
    DEPENDENCIES.clear()


def test_ignore_required_dependencies_in_init():

    class TestService(Service):
        __dependencies__ = ('some_dep',)
        __required__ = ('some_dep',)

    assert TestService()


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


def test_start_used_dependencies_only():

    @dependency
    async def not_used():
        raise RuntimeError("Shouldn't been used")
        yield

    @dependency
    async def used():
        yield

    class TestService(Service):
        __dependencies__ = ('used',)

        async def start(self):
            ...

    with entrypoint(TestService()):
        ...


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
