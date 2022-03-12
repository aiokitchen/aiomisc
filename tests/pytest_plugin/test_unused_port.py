import platform
import socket


if platform.system() == "Windows":
    MAX_FILES = 1024
else:
    import resource

    MAX_FILES = 1024

    # Ignore opened files by pytest and others
    NFILE_SHIFT = 256
    resource.setrlimit(
        resource.RLIMIT_NOFILE, (MAX_FILES + NFILE_SHIFT, 65535),
    )


async def test_many_ports(aiomisc_unused_port_factory, localhost):
    tries = MAX_FILES
    ports = set()

    for _ in range(tries):
        port = aiomisc_unused_port_factory()
        assert port not in ports
        ports.add(port)

        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((localhost, port))

    assert len(ports) == tries
