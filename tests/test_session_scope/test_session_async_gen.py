"""
Regression test for https://github.com/aiokitchen/aiomisc/issues/243

Function-scoped entrypoint fixture must not call shutdown_asyncgens
on a session-scoped event loop, because that destroys session-scoped
async generator fixtures that are still alive.
"""
import pytest


async def some_agen():
    for i in range(100):
        yield i + 1


@pytest.fixture(scope="session")
async def async_gen_fixture():
    agen = some_agen()

    val = await agen.__anext__()
    assert val == 1
    val = await agen.__anext__()
    assert val == 2
    yield val
    new_val = await agen.__anext__()
    assert new_val == 3
    await agen.aclose()


async def test_async_gen_first(async_gen_fixture):
    assert async_gen_fixture == 2


async def test_async_gen_second(async_gen_fixture):
    assert async_gen_fixture == 2
