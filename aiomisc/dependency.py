import abc
import asyncio
import inspect
from types import MappingProxyType


DEPENDENCIES = {}


class BaseDependencyState:

    @abc.abstractmethod
    def __init__(self, func):
        ...

    @abc.abstractmethod
    async def start(self):
        ...

    @abc.abstractmethod
    async def stop(self):
        ...

    @staticmethod
    def create(func):
        if inspect.isasyncgenfunction(func):
            return GeneratorDependencyState(func)
        elif inspect.iscoroutinefunction(func):
            return CoroutineDependencyState(func)

        raise RuntimeError('%r is not async generator or coroutine', func)


class GeneratorDependencyState(BaseDependencyState):

    __slots__ = ('dependency', 'generator')

    def __init__(self, func):
        self.generator = func()

    async def start(self):
        self.dependency = await self.generator.asend(None)

    async def stop(self):
        try:
            await self.generator.asend(None)
        except StopAsyncIteration:
            ...


class CoroutineDependencyState(BaseDependencyState):

    __slots__ = ('dependency', 'func')

    def __init__(self, func):
        self.func = func

    async def start(self):
        self.dependency = await self.func()

    async def stop(self):
        ...


def dependency(f):
    DEPENDENCIES[f.__name__] = f
    return f


async def start_dependencies(names, loop=None):
    if loop is None:
        loop = asyncio.get_event_loop()

    dependencies = dict()
    setup = []
    for name in names:
        if name not in DEPENDENCIES:
            raise RuntimeError("Dependency %s wasn't found", name)
        dependencies[name] = BaseDependencyState.create(DEPENDENCIES[name])
        setup.append(dependencies[name].start())

    await asyncio.gather(*setup, loop=loop)

    loop._aiomisc_dependencies = MappingProxyType(dependencies)


def get_dependencies(names, loop=None):
    loop = asyncio.get_event_loop()

    return {name: loop._aiomisc_dependencies[name].dependency for name in names}


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
