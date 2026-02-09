Periodic Services
=================

This section covers services for periodic and scheduled task execution.


.. _periodic-service:

``PeriodicService``
+++++++++++++++++++

``PeriodicService`` runs ``PeriodicCallback`` as a service and waits for
the running callback to complete on the stop method. You need to use ``PeriodicService``
as a base class and override ``callback`` async coroutine method.

Service class accepts required ``interval`` argument - periodic interval
in seconds and
optional ``delay`` argument - periodic execution delay in seconds (0 by default).

.. code-block:: python

    import aiomisc
    from aiomisc.service.periodic import PeriodicService


    class MyPeriodicService(PeriodicService):
        async def callback(self):
            log.info('Running periodic callback')
            # ...

    service = MyPeriodicService(interval=3600, delay=0)  # once per hour

    with entrypoint(service) as loop:
        loop.run_forever()


.. _dns_server:

DNS Server
++++++++++

The DNS server described here uses the ``aiomisc`` library, which provides
utilities for asynchronous I/O operations, and the ``dnslib`` library for
handling DNS records and packets. This setup is ideal for high-performance,
non-blocking DNS query handling.

Key Features
~~~~~~~~~~~~

1. **Asynchronous I/O**: Utilizes asynchronous operations to handle multiple
   DNS queries concurrently, ensuring high performance and scalability.
2. **UDP and TCP Support**: Supports DNS queries over both UDP and TCP
   protocols, making it versatile for various network configurations.
3. **``EDNS0`` Support**: Implements Extension Mechanisms for DNS (``EDNS0``)
   to handle larger DNS messages and extended functionalities.
4. **Customizable DNS Records**: Allows easy configuration of DNS zones
   and records, enabling you to define and manage your DNS entries
   efficiently.

Prerequisites
~~~~~~~~~~~~~

Install the required libraries using pip:

.. code-block::

    pip install aiomisc[dns]


Setting Up the Server
~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    from aiomisc import entrypoint
    from aiomisc.service.dns import (
        DNSStore, DNSZone, TCPDNSServer, UDPDNSServer, records,
    )

    zone = DNSZone("test.")
    zone.add_record(records.A.create("test.", "10.10.10.10"))
    zone.add_record(records.AAAA.create("test.", "fd10::10"))

    store = DNSStore()
    store.add_zone(zone)
    services = [
        UDPDNSServer(
            store=store, address="::1", port=5053,
        ),
        TCPDNSServer(
            store=store, address="::1", port=5053,
        ),
    ]

    if __name__ == "__main__":
        with entrypoint(*services, log_level="debug") as loop:
            loop.run_forever()


Testing the Server
~~~~~~~~~~~~~~~~~~

You can test the DNS server using tools like ``dig``. For example,
to query the A and AAAA records for ``test.``,
use the following commands:

.. code-block::

    dig @::1 -p 5053 test. A
    dig @::1 -p 5053 test. AAAA
    dig @::1 -p 5053 +tcp test. A
    dig @::1 -p 5053 +tcp test. AAAA


These commands should return the IP addresses
``10.10.10.10`` and ``fd10::10`` respectively, confirming that the
DNS server is working correctly.


Dynamic Store Management
~~~~~~~~~~~~~~~~~~~~~~~~

One of the powerful features of this DNS server setup is the
ability to dynamically manage the DNS store. This allows you
to add or remove zones and records at runtime, without needing
to restart the server.

Managing DNS zones and records dynamically is essential for a
flexible DNS server setup. This guide focuses on how to
manipulate DNS zones and records using the ``DNSStore`` and ``DNSZone``
classes, providing practical examples for each operation.


Adding a Zone
~~~~~~~~~~~~~

You can add a new zone to the ``DNSStore`` to manage its records.
This operation ensures that the zone is available for DNS queries.

.. code-block:: python

    from aiomisc.service.dns import DNSStore, DNSZone

    # Create a DNSStore instance
    dns_store = DNSStore()

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Verify the zone is added
    assert dns_store.get_zone("example.com.") is zone


Removing a Zone
~~~~~~~~~~~~~~~

Removing a zone from the ``DNSStore`` ensures it is no longer available for DNS queries.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Remove the zone from the store
    dns_store.remove_zone("example.com.")

    # Verify the zone is removed
    assert dns_store.get_zone("example.com.") is None


Adding a Record to a Zone
~~~~~~~~~~~~~~~~~~~~~~~~~

To manage DNS entries, you can add records to a specific zone.
This operation makes the record available for DNS resolution within that zone.

.. code-block:: python

    from aiomisc.service.dns.records import A, RecordType

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record
    record = A.create(name="www.example.com.", ip="192.0.2.1")

    # Add the record to the zone
    zone.add_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the record
    records = dns_store.query("www.example.com.", RecordType.A)

    # Verify the record is added
    assert record in records


Querying Records
~~~~~~~~~~~~~~~~

You can query the ``DNSStore`` to retrieve records for a specific domain
name. This is useful to verify if a record exists or to handle DNS queries.

.. code-block:: python

    # Query the store for a nonexistent record
    records = dns_store.query("nonexistent.example.com.", RecordType.A)

    # Verify no records are found
    assert len(records) == 0


Handling Duplicate Zones
~~~~~~~~~~~~~~~~~~~~~~~~

Attempting to add a zone that already exists should raise an error,
ensuring that each zone is unique within the ``DNSStore``.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Attempt to add the same zone again
    try:
        dns_store.add_zone(zone)
    except ValueError as e:
        print(f"Error: {e}")


Removing a Nonexistent Zone
~~~~~~~~~~~~~~~~~~~~~~~~~~~

Removing a zone that does not exist should raise an error,
indicating that the operation is invalid.

.. code-block:: python

    # Attempt to remove a nonexistent zone
    try:
        dns_store.remove_zone("nonexistent.com.")
    except ValueError as e:
        print(f"Error: {e}")


Querying Subdomains
~~~~~~~~~~~~~~~~~~~

The ``DNSStore`` supports querying subdomains, allowing you to resolve
records within subdomains of an existing zone.

.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record for a subdomain
    record = A.create(name="sub.example.com.", ip="192.0.2.2")

    # Add the record to the zone
    zone.add_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the subdomain record
    records = dns_store.query("sub.example.com.", RecordType.A)

    # Verify the subdomain record is found
    assert record in records


Retrieving a Zone
~~~~~~~~~~~~~~~~~

You can retrieve a zone from the ``DNSStore`` to
inspect or manipulate it further.

.. code-block:: python

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Retrieve the zone from the store
    retrieved_zone = dns_store.get_zone("example.com.")

    # Verify the zone is retrieved
    assert retrieved_zone is zone


Handling Nonexistent Zones
~~~~~~~~~~~~~~~~~~~~~~~~~~

Retrieving a zone that does not exist should return ``None``.

.. code-block:: python

    # Attempt to retrieve a nonexistent zone
    nonexistent_zone = dns_store.get_zone("nonexistent.com.")

    # Verify no zone is retrieved
    assert nonexistent_zone is None


Removing a Record from a Zone
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To remove a DNS record from a zone, you can use the
``remove_record`` method. This operation ensures the
record is no longer available for DNS resolution.


.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Create an A record
    record = A.create(name="www.example.com.", ip="192.0.2.1")

    # Add the record to the zone
    zone.add_record(record)

    # Remove the record from the zone
    zone.remove_record(record)

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Query the store for the record
    records = dns_store.query("www.example.com.", RecordType.A)

    # Verify the record is removed
    assert len(records) == 0


Finding Zone by Prefix
~~~~~~~~~~~~~~~~~~~~~~

The ``DNSStore`` can find the appropriate zone for a given domain
name, which is useful for handling queries with subdomains.


.. code-block:: python

    # Create a DNSZone instance
    zone = DNSZone("example.com.")

    # Add the zone to the store
    dns_store.add_zone(zone)

    # Find the zone for a subdomain
    zone_prefix = dns_store.get_zone_for_name("sub.example.com.")

    # Verify the correct zone is found
    assert zone_prefix == ("com", "example")

.. _cron-service:

``CronService``
+++++++++++++++

``CronService`` runs ``CronCallback's`` as a service and waits for
running callbacks to complete on the stop method.

It's based on croniter_. You can register async coroutine method with ``spec`` argument - cron like format:

.. _croniter: https://github.com/taichino/croniter

.. warning::

   requires installed croniter_:

   .. code-block::

       pip install croniter

   or using extras:

   .. code-block::

       pip install aiomisc[cron]


.. code-block:: python

    import aiomisc
    from aiomisc.service.cron import CronService


    async def callback():
        log.info('Running cron callback')
        # ...

    service = CronService()
    service.register(callback, spec="0 * * * *") # every hour at zero minutes

    with entrypoint(service) as loop:
        loop.run_forever()


You can also inherit from ``CronService``, but remember that callback registration
should be performed before start

.. code-block:: python

    import aiomisc
    from aiomisc.service.cron import CronService


    class MyCronService(CronService):
        async def callback(self):
            log.info('Running cron callback')
            # ...

        async def start(self):
            self.register(self.callback, spec="0 * * * *")
            await super().start()

    service = MyCronService()

    with entrypoint(service) as loop:
        loop.run_forever()
