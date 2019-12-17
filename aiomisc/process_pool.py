import asyncio
import os
import pickle
import socket
import struct
import uuid
import logging
from concurrent.futures._base import Executor
from multiprocessing import Process, cpu_count, ProcessError
from tempfile import mktemp


HEADER = struct.Struct("!Q")


def create_socket():
    try:
        return socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    except:
        return socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def _process_inner(addr, secret, serealizer, deserializer):
    logging.basicConfig(level=logging.DEBUG)

    log = logging.getLogger().getChild(str(os.getpid()))
    log.debug("Process spawned with PID=%r", os.getpid())

    with create_socket() as sock:
        log.debug("Connecting to %r", addr)
        sock.connect(addr)

        log.debug("Authenticating")
        sock.send(secret)
        del secret, addr

        def read():
            size = HEADER.unpack(sock.recv(HEADER.size))[0]
            return sock.recv(size)

        def write(payload):
            sock.send(HEADER.pack(len(payload)))
            sock.send(payload)

        while True:
            cid, func, args, kwargs = deserializer(read())
            log.debug("Executing id=%s func=%r", cid, func)

            try:
                write(serealizer((cid, False, func(*args, **kwargs))))
            except BaseException as e:
                write(serealizer((cid, True, e)))
            finally:
                del cid, func, args, kwargs


class ProcessPoolExecutor(Executor):
    MAX_WORKERS = max((cpu_count(), 4))
    SECRET_LENGTH = 64

    SERIALIZER = pickle.dumps
    DESERIALIZER = pickle.loads

    @staticmethod
    def _bind_socket():
        sock = create_socket()

        if sock.family is socket.AF_INET:
            sock.bind(("127.0.0.1", 0))
            address = sock.getsockname()
        else:
            address = mktemp(suffix=".sock")
            sock.bind(address)
            os.chmod(address, 0o700)

        sock.setblocking(False)
        return sock, address

    def __repr__(self):
        return "<{} size={}: {!r}>".format(
            self.__class__.__name__, len(self.__pool), self.__sock.family
        )

    def _create_task(self, coro):
        task = self.__loop.create_task(coro)
        self.__tasks.add(task)
        task.add_done_callback(self.__tasks.remove)
        return task

    def __init__(self, max_workers=MAX_WORKERS, loop=None):
        self.__max_workers = max_workers

        self.__futures = {}
        self.__sock, self.__address = self._bind_socket()

        self.__pool = set()
        self.__waiters = {}

        self.__tasks = set()
        self.__closed = False

        self.__loop = loop or asyncio.get_event_loop()
        self.__server_start_event = asyncio.Event()
        self.__read_queue = asyncio.Queue()
        self.__write_queue = asyncio.Queue()

        # noinspection PyTypeChecker
        self.__server = None    # type: asyncio.AbstractServer

        self._create_task(self.start())

    async def start(self):
        self.__server = await asyncio.start_server(
            lambda *a: self._create_task(self.__on_connect(*a)),
            sock=self.__sock,
        )

        await asyncio.gather(
            *[self._spawn() for _ in range(self.__max_workers)]
        )
        self._create_task(self._read_results())

    async def _read_results(self):
        while True:
            cid, fail, obj = await self.__read_queue.get()
            future = self.__futures.pop(cid)

            if future.done():
                continue

            if fail:
                future.set_exception(obj)
            else:
                future.set_result(obj)

    async def _spawn(self):
        secret = os.urandom(self.SECRET_LENGTH)

        process = Process(
            target=_process_inner,
            args=(self.__address, secret, self.SERIALIZER, self.DESERIALIZER),
        )
        self.__pool.add(process)

        self.__waiters[secret] = self.__loop.create_future()
        self.__loop.call_soon(process.start)

        reader, writer = await self.__waiters[secret]
        close_event = asyncio.Event()

        async def handler_read():
            while True:
                try:
                    size = HEADER.unpack(
                        await reader.readexactly(HEADER.size)
                    )[0]
                    payload = self.DESERIALIZER(await reader.readexactly(size))
                    await self.__read_queue.put(payload)
                    del payload, size
                except asyncio.IncompleteReadError:
                    close_event.set()

        async def handler_write():
            while True:
                payload = await self.__write_queue.get()
                size = HEADER.pack(len(payload))

                try:
                    writer.write(size)
                    writer.write(payload)
                    await writer.drain()
                except Exception:
                    cid = self.DESERIALIZER(payload)[0]
                    close_event.set()
                    future = self.__futures.pop(cid, None)
                    if future is None or future.done():
                        return

                    future.set_exception(
                        ProcessError('Process terminated', process.exitcode)
                    )
                    return
                finally:
                    del payload, size

        async def on_close():
            await close_event.wait()
            if self.__closed:
                return

            await self._spawn()

        self._create_task(handler_write())
        self._create_task(handler_read())
        self._create_task(on_close())

        logging.debug("Spawned")

    async def __on_connect(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ):

        secret = await reader.readexactly(self.SECRET_LENGTH)
        waiter = self.__waiters.pop(secret, None)

        if waiter is None:
            writer.close()
            return

        waiter.set_result((reader, writer))

    def submit(self, fn, *args, **kwargs):
        if self.__closed:
            raise RuntimeError("Pool closed")

        if fn is None or not callable(fn):
            raise ValueError("First argument must be callable")

        future = self.__loop.create_future()  # type: asyncio.Future

        cid = uuid.uuid4().int
        self.__futures[cid] = future
        self.__write_queue.put_nowait(
            self.SERIALIZER((cid, fn, args, kwargs))
        )

        return future

    def shutdown(self, wait=True):
        if self.__closed:
            return

        self.__closed = True
        self.__server.close()

        for prc in self.__pool:
            prc.terminate()

        for f in self.__futures.values():
            if f.done():
                continue

            f.set_exception(asyncio.CancelledError())

        for task in self.__tasks:
            if task.done():
                continue

            task.cancel()

        if wait:
            for prc in self.__pool:
                prc.join()

    def __del__(self):
        self.shutdown()
