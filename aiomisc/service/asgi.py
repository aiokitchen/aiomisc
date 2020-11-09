from aiohttp.web import Application
from aiohttp_asgi import ASGIResource
from aiohttp_asgi.resource import ASGIApplicationType

from .aiohttp import AIOHTTPService, AIOHTTPSSLService


def _create_app(asgi_app: ASGIApplicationType) -> Application:
    app = Application()
    asgi_resource = ASGIResource(asgi_app, root_path="/")
    app.router.register_resource(asgi_resource)
    asgi_resource.lifespan_mount(app, startup=True, shutdown=True)
    return app


class ASGIHTTPService(AIOHTTPService):
    __async_required__ = "start", "create_application", "create_asgi_app"

    async def create_asgi_app(self) -> ASGIApplicationType:
        raise NotImplementedError(
            "You must implement "
            '"create_asgi_app" method',
        )

    async def create_application(self) -> Application:
        return _create_app(await self.create_asgi_app())


class ASGIHTTPSSLService(AIOHTTPSSLService):
    __async_required__ = "start", "create_application", "create_asgi_app"

    async def create_asgi_app(self) -> ASGIApplicationType:
        raise NotImplementedError(
            "You must implement "
            '"create_asgi_app" method',
        )

    async def create_application(self) -> Application:
        return _create_app(await self.create_asgi_app())
