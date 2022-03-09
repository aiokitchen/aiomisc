import pytest

from aiomisc import entrypoint


class TestSessionScopeAsyncGenFixture:

    @pytest.fixture(scope="session")
    def loop(self):
        with entrypoint() as loop:
            yield loop

    @pytest.fixture(scope="session")
    async def fixture(self):
        yield

    async def test_using_fixture(self, fixture):
        pass

    async def test_not_using_fixture(self):
        pass
