DoH server
==========

DNS over HTTPS simple server.

```shell
doh_server.py [-h] [--address ADDRESS] [--port PORT]
                     [--doh-server DOH_SERVER]
                     [--log-level {debug,info,warning,error,critical}]

options:
  -h, --help            show this help message and exit
  --address ADDRESS     (default: 127.0.0.1) [ENV: DOH_ADDRESS]
  --port PORT           (default: 25353) [ENV: DOH_PORT]
  --doh-server DOH_SERVER
                        (default: https://1.1.1.1/dns-query) [ENV:
                        DOH_DOH_SERVER]
  --log-level {debug,info,warning,error,critical}
                        (default: info) [ENV: DOH_LOG_LEVEL]

Default values will based on following configuration files (). The
configuration files is INI-formatted files where configuration groups is INI
sections.See more https://pypi.org/project/argclass/#configs

```

Installation
------------

You might use pre-build docker image:

```shell
$ docker run --rm -it -p 5353:53/udp mosquito/doh-server
```

and test it

```shell
$ dig @127.0.0.1 -p 5353 google.com
```

or install it to the server:

```shell
$ python3.8 -m venv /usr/share/python3/doh
$ /usr/share/python3/doh/bin/pip install -U pip \
    aiomisc~=15.6.1 \
    aiohttp~=3.8.0 \
    argclass~=0.6.0
$ cp doh_server.py /usr/share/python3/doh/bin/doh-server
$ ln -snf /usr/share/python3/doh/bin/doh-server /usr/local/bin/doh-server
```
