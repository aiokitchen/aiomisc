Network Services
================

This section covers network-related services including TCP, UDP, and TLS
servers and clients.


.. _tcp-server:

``TCPServer``
+++++++++++++

``TCPServer`` - it's a base class for writing TCP servers.
Just implement ``handle_client(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_tcp_server

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer


    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    async def echo_client(host, port):
        reader, writer = await asyncio.open_connection(host=host, port=port)
        writer.write(b"hello\n")
        assert await reader.readline() == b"hello\n"

        writer.write(b"world\n")
        assert await reader.readline() == b"world\n"

        writer.close()
        await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(echo_client("localhost", 8901))


.. _udp-server:

``UDPServer``
+++++++++++++

``UDPServer`` - it's a base class for writing UDP servers.
Just implement ``handle_datagram(data, addr)`` to use it.

.. code-block:: python

    class UDPPrinter(UDPServer):
        async def handle_datagram(self, data: bytes, addr):
            print(addr, '->', data)


    with entrypoint(UDPPrinter(address='localhost', port=3000)) as loop:
        loop.run_forever()


``TLSServer``
+++++++++++++

``TLSServer`` - it's a base class for writing TCP servers with TLS.
Just implement ``handle_client(reader, writer)`` to use it.

.. code-block:: python

    class SecureEchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while True:
                writer.write(await reader.readline())

    service = SecureEchoServer(
        address='localhost',
        port=8900,
        ca='ca.pem',
        cert='cert.pem',
        key='key.pem',
        verify=False,
    )

    with entrypoint(service) as loop:
        loop.run_forever()


.. _tcp-client:

``TCPClient``
+++++++++++++

``TCPClient`` - it's a base class for writing TCP clients.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_tcp_client

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, TCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(TCPClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
        EchoClient(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``TLSClient``
+++++++++++++

``TLSClient`` - it's a base class for writing TLS clients.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, TCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(TLSClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='server.pem',
            key='server.key',
        ),
        EchoClient(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='client.pem',
            key='client.key',
        ),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``RobustTCPClient``
+++++++++++++++++++

``RobustTCPClient`` - it's a base class for writing TCP clients with
auto-reconnection when connection lost.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python
    :name: test_service_echo_robust_tcp_client

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, RobustTCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TCPServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(RobustTCPClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(address='localhost', port=8901),
        EchoClient(address='localhost', port=8901),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))


``RobustTLSClient``
+++++++++++++++++++

``RobustTLSClient`` - it's a base class for writing TLS clients with
auto-reconnection when connection lost.
Just implement ``handle_connection(reader, writer)`` to use it.

.. code-block:: python

    import asyncio
    import logging
    from aiomisc import entrypoint
    from aiomisc.service import TCPServer, RobustTCPClient

    log = logging.getLogger(__name__)


    class EchoServer(TLSServer):
        async def handle_client(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter):
            while not reader.at_eof():
                writer.write(await reader.read(255))

            log.info("Client connection closed")


    class EchoClient(RobustTLSClient):

        async def handle_connection(self, reader: asyncio.StreamReader,
                                    writer: asyncio.StreamWriter) -> None:
            writer.write(b"hello\n")
            assert await reader.readline() == b"hello\n"

            writer.write(b"world\n")
            assert await reader.readline() == b"world\n"

            writer.write_eof()
            writer.close()
            await writer.wait_closed()


    with entrypoint(
        EchoServer(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='server.pem',
            key='server.key',
        ),
        EchoClient(
            address='localhost', port=8901,
            ca='ca.pem',
            cert='client.pem',
            key='client.key',
        ),
    ) as loop:
        loop.run_until_complete(asyncio.sleep(0.1))
