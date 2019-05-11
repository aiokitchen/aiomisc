from collections import namedtuple
from functools import wraps

from aiodine.store import Store


STORE = Store()

NOT_FOUND_DEP = object()


def dependency(func):
    return STORE.provider(scope='session')(func)


async def inject(target, dependencies):

    deps_holder = namedtuple(
        'DepsHolder', dependencies,
        defaults=([NOT_FOUND_DEP] * len(dependencies)),
    )

    @wraps(deps_holder)
    async def async_deps_holder(*args):
        return deps_holder(*args)

    resolved_deps = await STORE.consumer(async_deps_holder)()

    for name in dependencies:
        value = getattr(resolved_deps, name)
        if not hasattr(target, name):
            if value is NOT_FOUND_DEP:
                raise RuntimeError("Required %s dependency wasn't found", name)

            setattr(target, name, value)


async def enter_session():
    return await STORE.enter_session()


async def exit_session():
    return await STORE.exit_session()


def freeze():
    return STORE.freeze()


def consumer(*args, **kwargs):
    return STORE.consumer(*args, **kwargs)


def reset_store():
    global STORE
    STORE = Store()


__all__ = (
    'dependency', 'enter_session', 'exit_session', 'freeze', 'consumer',
    'inject', 'reset_store',
)
