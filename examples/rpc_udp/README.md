
RPC Server
==========

Simple RPC server and client over UDP implementation using `msgpack-python`

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
[T:MainThread] INFO:aiomisc.utils: Listening udp://[::]:15678
```

Start client
--------------

```bash
$ python3 -m rpc.client
[T:MainThread] INFO:client: Starting reply server at udp://::1:51548
[T:MainThread] INFO:client: Total executed 90000 requests on 2.491
[T:MainThread] INFO:client: RPS: 36124.397
[T:MainThread] INFO:client: Close connection
```

