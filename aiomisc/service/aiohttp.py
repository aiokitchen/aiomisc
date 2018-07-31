import socket

from aiohttp.web import Application, AppRunner, SockSite
from aiohttp.helpers import AccessLogger

from .base import Service
from ..utils import bind_socket


class AIOHTTPService(Service):
    __async_required__ = frozenset({'start', 'create_application'})

    def __init__(self, address: str = None, port: int = None,
                 sock: socket.socket = None, shutdown_timeout: int = 5):

        if not sock:
            if not (address and port):
                raise RuntimeError(
                    'You should pass socket instance or '
                    '"address" and "port" couple'
                )

            self.socket = bind_socket(
                address=address,
                port=port,
                proto_name='http',
            )

        elif not isinstance(sock, socket.socket):
            raise ValueError('sock must be socket instance')
        else:
            self.socket = sock

        self.runner = None
        self.shutdown_timeout = shutdown_timeout

        super().__init__()

    async def create_application(self) -> Application:
        raise NotImplementedError('You should implement '
                                  '"create_application" method')

    async def start(self):
        self.runner = AppRunner(
            await self.create_application(),
            access_log_class=AccessLogger,
            access_log_format=AccessLogger.LOG_FORMAT,
        )

        await self.runner.setup()

        site = SockSite(
            self.runner, self.socket,
            shutdown_timeout=self.shutdown_timeout
        )

        await site.start()

    async def stop(self, exception: Exception):
        await self.runner.cleanup()
