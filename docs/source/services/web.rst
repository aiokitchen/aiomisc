Web Services
============

This section covers web-related services including aiohttp, ASGI, and Uvicorn.


.. _aiohttp-service:

aiohttp service
+++++++++++++++

.. warning::

   requires installed aiohttp:

   .. code-block::

       pip install aiohttp

   or using extras:

   .. code-block::

       pip install aiomisc[aiohttp]


aiohttp application can be started as a service:

.. code-block:: python

    import aiohttp.web
    import argparse
    from aiomisc import entrypoint
    from aiomisc.service.aiohttp import AIOHTTPService

    parser = argparse.ArgumentParser()
    group = parser.add_argument_group('HTTP options')

    group.add_argument("-l", "--address", default="::",
                       help="Listen HTTP address")
    group.add_argument("-p", "--port", type=int, default=8080,
                       help="Listen HTTP port")


    async def handle(request):
        name = request.match_info.get('name', "Anonymous")
        text = "Hello, " + name
        return aiohttp.web.Response(text=text)


    class REST(AIOHTTPService):
        async def create_application(self):
            app = aiohttp.web.Application()

            app.add_routes([
                aiohttp.web.get('/', handle),
                aiohttp.web.get('/{name}', handle)
            ])

            return app

    arguments = parser.parse_args()
    service = REST(address=arguments.address, port=arguments.port)

    with entrypoint(service) as loop:
        loop.run_forever()


Class ``AIOHTTPSSLService`` is similar to ``AIOHTTPService`` but creates an HTTPS
server. You must pass SSL-required options (see ``TLSServer`` class).


.. _asgi-service:

asgi service
++++++++++++

.. warning::

   requires installed aiohttp-asgi:

   .. code-block::

       pip install aiohttp-asgi

   or using extras:

   .. code-block::

       pip install aiomisc[asgi]


Any ASGI-like application can be started as a service:

.. code-block:: python

   import argparse

   from fastapi import FastAPI

   from aiomisc import entrypoint
   from aiomisc.service.asgi import ASGIHTTPService, ASGIApplicationType

   parser = argparse.ArgumentParser()
   group = parser.add_argument_group('HTTP options')

   group.add_argument("-l", "--address", default="::",
                      help="Listen HTTP address")
   group.add_argument("-p", "--port", type=int, default=8080,
                      help="Listen HTTP port")


   app = FastAPI()


   @app.get("/")
   async def root():
       return {"message": "Hello World"}


   class REST(ASGIHTTPService):
       async def create_asgi_app(self) -> ASGIApplicationType:
           return app


   arguments = parser.parse_args()
   service = REST(address=arguments.address, port=arguments.port)

   with entrypoint(service) as loop:
       loop.run_forever()


Class ``ASGIHTTPSSLService`` is similar to ``ASGIHTTPService`` but creates
HTTPS server. You must pass SSL-required options (see ``TLSServer`` class).

.. uvicorn-service:

uvicorn service
+++++++++++++++

.. warning::

   requires installed uvicorn:

   .. code-block::

       pip install uvicorn

   or using extras:

   .. code-block::

       pip install aiomisc[uvicorn]


Any ASGI-like application can be started via uvicorn as a service:

.. code-block:: python

   import argparse

   from fastapi import FastAPI

   from aiomisc import entrypoint
   from aiomisc.service.uvicorn import UvicornApplication, UvicornService

   parser = argparse.ArgumentParser()
   group = parser.add_argument_group('HTTP options')

   group.add_argument("-l", "--host", default="::",
                      help="Listen HTTP host")
   group.add_argument("-p", "--port", type=int, default=8080,
                      help="Listen HTTP port")


   app = FastAPI()


   @app.get("/")
   async def root():
       return {"message": "Hello World"}


   class REST(UvicornService):
       async def create_application(self) -> UvicornApplication:
           return app


   arguments = parser.parse_args()
   service = REST(host=arguments.host, port=arguments.port)

   with entrypoint(service) as loop:
       loop.run_forever()
