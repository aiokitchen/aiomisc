
RPC Server
==========

Simple two-way RPC server and client implementation using `msgspec`

Requirements
-----------------

Install dependencies:

```bash
pip install aiomisc msgspec rich
```

Start server
--------------

```bash
$ python3 -m rpc.server
[22:25:24] INFO     Listening tcp://[::]:5678                       utils.py:144
[22:25:29] INFO     Start communication with tcp://[::1]:62121       spec.py:154
```

Start client
--------------

```bash
$ python3 -m rpc.client
[22:25:29] INFO     Connected to tcp://::1:5678                       tcp.py:106
           INFO     Start communication with tcp://[::1]:5678        spec.py:154
[22:25:40] INFO     Communication with tcp://[::1]:5678 finished     spec.py:176
[22:25:40] INFO     Total executed 1000000 requests on 10.623       client.py:38
           INFO     RPS: 94139.165                                  client.py:39
           INFO     Close connection                                client.py:40
```

