Abstract connection pool
========================

``aiomisc.PoolBase`` is an abstract class for implementing user-defined
connection pool.


Example for ``aioredis``:

.. code-block:: python

    import asyncio
    import aioredis
    import aiomisc


    class RedisPool(aiomisc.PoolBase):
        def __init__(self, uri, maxsize=10, recycle=60):
            super().__init__(maxsize=maxsize, recycle=recycle)
            self.uri = uri

        async def _create_instance(self):
            return await aioredis.create_redis(self.uri)

        async def _destroy_instance(self, instance: aioredis.Redis):
            instance.close()
            await instance.wait_closed()

        async def _check_instance(self, instance: aioredis.Redis):
            try:
                await asyncio.wait_for(instance.ping(1), timeout=0.5)
            except:
                return False

            return True


    async def main():
        pool = RedisPool("redis://localhost")
        async with pool.acquire() as connection:
            await connection.set("foo", "bar")

        async with pool.acquire() as connection:
            print(await connection.get("foo"))


    asyncio.run(main())
