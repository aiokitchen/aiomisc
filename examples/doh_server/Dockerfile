FROM snakepacker/python:all as builder

RUN python3.10 -m venv /usr/share/python3/doh

RUN /usr/share/python3/doh/bin/pip install -U pip \
    aiomisc~=15.6.1 \
    aiohttp~=3.8.0 \
    argclass~=0.6.0

RUN find-libdeps /usr/share/python3/doh > /usr/share/python3/doh/pkgdeps.txt

COPY doh_server.py /usr/share/python3/doh/bin/doh-server
RUN chmod a+x /usr/share/python3/doh/bin/doh-server

###############################################################################
FROM snakepacker/python:3.10

COPY --from=builder /usr/share/python3/doh /usr/share/python3/doh

RUN xargs -ra /usr/share/python3/doh/pkgdeps.txt apt-install
RUN ln -snf /usr/share/python3/doh/bin/doh-server /usr/bin/doh-server

ENV DOH_ADDRESS="0.0.0.0"
ENV DOH_PORT="53"
ENV DOH_URL="https://1.1.1.1/dns-query"

CMD ["/usr/bin/doh-server"]
