
RPC Server
==========

Simple RPC server and client implementation using `msgpack-python`

Requirements
-----------------

Install dependencies:

```bash
pip install aiomisc msgspec
```

Start server
--------------

```bash
$ python3 -m rpc.server
[T:MainThread] INFO:aiomisc.utils: Listening tcp://[::]:5678
```

Start client
--------------

```bash
$ python3 -m rpc.client
[T:MainThread] INFO:client: Connecting to ::1:5678
[T:MainThread] INFO:client: Total executed 90000 requests on 4.419
[T:MainThread] INFO:client: RPS: 20368.524
[T:MainThread] INFO:client: Close connection
```

