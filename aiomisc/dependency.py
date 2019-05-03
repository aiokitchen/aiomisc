import asyncio
from types import MappingProxyType
from typing import Any
from functools import wraps


DEPENDENCIES = {}


class DependencyState:

    __slots__ = ('dependency', 'generator')

    def __init__(self, dep_func):
        self.generator = dep_func()

    async def start(self):
        self.dependency = await self.generator.asend(None)

    async def stop(self):
        try:
            await self.generator.asend(None)
        except StopAsyncIteration:
            ...


def dependency(f):
    DEPENDENCIES[f.__name__] = f
    return f


async def start_dependencies(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    deps = dict()
    setup = []
    for dep_name, dep_func in DEPENDENCIES.items():
        deps[dep_name] = DependencyState(dep_func)
        setup.append(deps[dep_name].start())

    await asyncio.gather(*setup, loop=loop)

    loop._aiomisc_dependencies = MappingProxyType(deps)



async def get_dependencies(deps, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    result = dict()
    for dep_name in deps:
        if dep_name not in loop._aiomisc_dependencies:
            raise RuntimeError('Dependency %s not found', dep_name)

        result[dep_name] = loop._aiomisc_dependencies[dep_name].dependency

    return result


async def stop_dependencies(loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()
    if not hasattr(loop, '_aiomisc_dependencies'):
        return

    halt = []
    for dep_state in loop._aiomisc_dependencies.values():
        halt.append(dep_state.stop())

    await asyncio.gather(*halt, return_exceptions=True)

    del loop._aiomisc_dependencies
