
RPC Server
==========

Simple RPC server and client over UDP implementation using `msgspec`

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
[12:26:34] INFO     Listening udp://[::]:15678                      utils.py:144
```

Start client
--------------

```bash
$ python3 -m rpc.client
[12:26:54] INFO     Listening udp://[::]:63609                      utils.py:144
[12:26:55] INFO     Total executed 90000 requests on 1.103          client.py:34
           INFO     RPS: 81589.949                                  client.py:35
           INFO     Close connection                                client.py:37
```

