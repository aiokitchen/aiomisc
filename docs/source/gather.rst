Gather
===============

<TBD>

.. code-block:: python
    :name: gather

    import aiomisc


    async def square(val):
        return val ** 2

    res = await aiomisc.gather(
        square(2), None, square(3),
    )
    assert res == [4, None, 9]


.. code-block:: python
    :name: gather_exception

    import aiomisc


    async def foo():
        return ValueError()

    res = await aiomisc.gather(
        None, foo(),
        return_exceptions=True,
    )
    assert res[0] is None
    assert isinstance(res[1], ValueError)
