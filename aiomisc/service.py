import asyncio
import socket

from .utils import bind_socket, OptionsType


class ServiceMeta(type):
    def __new__(cls, name, bases, namespace, **kwds):
        instance = type.__new__(cls, name, bases, dict(namespace))

        check_instance = all((
            asyncio.iscoroutinefunction(instance.start),
            asyncio.iscoroutinefunction(instance.stop),
        ))

        if not check_instance:
            raise TypeError(
                (
                    'The method of "%s.start" and "%s.stop" should '
                    'be coroutine functions'
                ) % (name, name)
            )

        return instance


class Service(metaclass=ServiceMeta):
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

    async def stop(self, exception: Exception=None):
        pass


class SimpleServer(Service):
    def __init__(self):
        self.server = None     # type: asyncio.AbstractServer
        super().__init__()

    async def start(self):
        raise NotImplementedError

    async def stop(self, exc: Exception=None):
        self.server.close()


class TCPServer(SimpleServer):
    PROTO_NAME = 'tcp'

    def __init__(self, address: str=None, port: int=None,
                 options: OptionsType = (), sock=None):
        if not sock:
            if not all((address, port)):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                address=address, port=port, options=options
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.socket = sock

        super().__init__()

    async def handle_client(self, reader: asyncio.StreamReader,
                            writer: asyncio.StreamWriter):
        raise NotImplementedError

    async def start(self):
        self.server = await asyncio.start_server(
            self.handle_client,
            sock=self.socket,
            loop=self.loop,
        )

    async def stop(self, exc: Exception=None):
        await super().stop(exc)
        await self.server.wait_closed()


class UDPServer(SimpleServer):
    class UDPSimpleProtocol(asyncio.DatagramProtocol):

        def __init__(self, handle_datagram):
            super().__init__()
            self.handler = asyncio.coroutine(handle_datagram)
            self.transport = None  # type: asyncio.DatagramTransport
            self.loop = None  # type: asyncio.AbstractEventLoop

        def connection_made(self, transport: asyncio.DatagramTransport):
            self.transport = transport
            self.loop = asyncio.get_event_loop()

        def datagram_received(self, data: bytes, addr: tuple):
            self.loop.create_task(self.handler(data, addr))

    def __init__(self, address: str=None, port: int=None,
                 options: OptionsType =(), sock=None):
        if not sock:
            if not all((address, port)):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                socket.AF_INET6 if ':' in address else socket.AF_INET,
                socket.SOCK_DGRAM,
                address=address, port=port, options=options,
            )
        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.socket = sock

        self.server = None
        self._protocol = None
        super().__init__()

    def handle_datagram(self, data: bytes, addr):
        raise NotImplementedError

    async def start(self):
        self.server, self._protocol = await self.loop.create_datagram_endpoint(
            lambda: UDPServer.UDPSimpleProtocol(self.handle_datagram),
            sock=self.socket,
        )
