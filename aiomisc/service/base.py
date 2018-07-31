import asyncio


class ServiceMeta(type):
    def __new__(cls, name, bases, namespace, **kwds):
        instance = type.__new__(cls, name, bases, dict(namespace))

        check_instance = all(
            asyncio.iscoroutinefunction(getattr(instance, method))
            for method in instance.__async_required__
        )

        if not check_instance:
            raise TypeError(
                'Following methods must be coroutine functions',
                tuple('%s.%s' % (name, m) for m in instance.__async_required__)
            )

        return instance


class Service(metaclass=ServiceMeta):
    __async_required__ = frozenset({'start', 'stop'})

    def __init__(self, **kwargs):
        self.loop = None
        self._set_params(**kwargs)

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    def _set_params(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    async def start(self):
        raise NotImplementedError

    async def stop(self, exception: Exception = None):
        pass


class SimpleServer(Service):
    def __init__(self):
        self.server = None
        super().__init__()

    async def start(self):
        raise NotImplementedError

    async def stop(self, exc: Exception = None):
        self.server.close()
