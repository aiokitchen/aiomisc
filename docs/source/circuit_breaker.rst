Circuit Breaker
===============

`Circuit breaker is a design pattern`_ used in software development.
It is used to detect failures and encapsulates the logic of preventing a
failure from constantly recurring, during maintenance, temporary external
system failure, or unexpected system difficulties.

The following example demonstrates the simple usage of the current
implementation of ``aiomisc.CircuitBreaker``.
An instance of ``CircuitBreaker`` collecting function call statistics.
That contains counters mapping with successful and failed function calls.
Function calls must be wrapped by the `CircuitBreaker.call`
the method to gather it.

Usage example:

.. code-block:: python
    :name: test_circuit_breaker

    from aiohttp import web, ClientSession
    from aiomisc.service.aiohttp import AIOHTTPService
    import aiohttp
    import aiomisc


    async def public_gists(request):
        async with aiohttp.ClientSession() as session:
            # Using as context manager
            with request.app["github_cb"].context():
                url = 'https://api.github.com/gists/public'
                async with session.get(url) as response:
                    data = await response.text()

        return web.Response(
            text=data,
            headers={"Content-Type": "application/json"}
        )


    class API(AIOHTTPService):
        async def create_application(self):
            app = web.Application()
            app.add_routes([web.get('/', public_gists)])

            # When 30% errors in 20 seconds
            # Will be broken for 5 seconds
            app["github_cb"] = aiomisc.CircuitBreaker(
                error_ratio=0.2,
                response_time=20,
                exceptions=[aiohttp.ClientError],
                broken_time=5
            )

            return app


    async def main():
        async with ClientSession() as session:
            async with session.get("http://localhost:8080/") as response:
                assert response.headers


    if __name__ == '__main__':
        with aiomisc.entrypoint(API(port=8080)) as loop:
            loop.run_until_complete(main())


.. _Circuit breaker is a design pattern: http://bit.ly/aimcbwiki


The `CircuitBreaker` object might be one of three states:

    * **PASSING**
    * **BROKEN**
    * **RECOVERING**

.. image:: /_static/cb-states.svg

**PASSING** means all calls will be passed as is and statistics will be gathered.
The next state will be determined after collecting statistics for
``passing_time`` seconds. If an effective error ratio is greater
than `error_ratio` then the next state will be set to **BROKEN**, otherwise,
it will remain unchanged.

**BROKEN** means the wrapped function won't be called and ``CircuitBroken``
an exception will be raised instead. **BROKEN** state will be kept
for ``broken_time`` seconds.

.. note::

    ``CircuitBroken`` exception is a consequence of **BROKEN** or **RECOVERY**
    state and never be accounted for in the statistic.

After that, it changes to **RECOVERING** state. While in that state, a small sample
of the wrapped function calls will be executed and statistics will be
gathered. If the effective error ratio after ``recovery_time`` is lower than
``error_ratio`` then the next state will be set to **PASSING**, and
otherwise - to **BROKEN**.

Argument ``exception_inspector`` is a function that is called whenever
an exception from the list of monitored exceptions occurs. When ``False``
will be returned, this exception will be ignored.

.. image:: /_static/cb-flow.svg


cutout
======

Decorator for ``CircuitBreaker`` which wrapping functions.

.. code-block:: python
    :name: test_cutout

    from aiohttp import web, ClientSession
    from aiomisc.service.aiohttp import AIOHTTPService
    import aiohttp
    import aiomisc


    # When 20% errors in 30 seconds
    # Will be broken on 30 seconds
    @aiomisc.cutout(0.2, 30, aiohttp.ClientError)
    async def fetch(session, url):
        async with session.get(url) as response:
            return await response.text()


    async def public_gists(request):
        async with aiohttp.ClientSession() as session:
            data = await fetch(
                session,
                'https://api.github.com/gists/public'
            )

        return web.Response(
            text=data,
            headers={"Content-Type": "application/json"}
        )


    class API(AIOHTTPService):
        async def create_application(self):
            app = web.Application()
            app.add_routes([web.get('/', public_gists)])
            return app


    async def main():
        async with ClientSession() as session:
            async with session.get("http://localhost:8080/") as response:
                assert response.headers


    if __name__ == '__main__':
        with aiomisc.entrypoint(API(port=8080)) as loop:
            loop.run_until_complete(main())
