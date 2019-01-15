import asyncio

from aiomisc.context import Context, get_context


class ServiceMeta(type):
    def __new__(cls, name, bases, namespace, **kwds):
        instance = type.__new__(cls, name, bases, dict(namespace))

        for key in ('__async_required__', '__required__'):
            setattr(instance, key, frozenset(getattr(instance, key, ())))

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
    __async_required__ = 'start', 'stop'
    __required__ = ()

    def __init__(self, **kwargs):
        lost_kw = self.__required__ - kwargs.keys()
        if lost_kw:
            raise AttributeError('Absent attributes', lost_kw)

        self.loop = None
        self._set_params(**kwargs)
        self.__context = None
        self.start_event = None       # type: asyncio.Event

    @property
    def context(self) -> Context:
        if self.__context is None:
            self.__context = get_context()
        return self.__context

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.start_event = asyncio.Event(loop=self.loop)

    def _set_params(self, **kwargs):
        for name, value in kwargs.items():
            setattr(self, name, value)

    async def start(self):
        raise NotImplementedError

    async def stop(self, exception: Exception = None):
        pass


class SimpleServer(Service):
    def __init__(self, **kwargs):
        self.server = None
        super().__init__(**kwargs)

    async def start(self):
        raise NotImplementedError

    async def stop(self, exc: Exception = None):
        self.server.close()
