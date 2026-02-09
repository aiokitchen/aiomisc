gRPC Service
============

.. _grpc-service:

GRPC service
++++++++++++

This is an example of a GRPC service which is defined in a file and loads a
`hello.proto` file without code generation, this example is one of the examples
from `grpcio`, the other examples will work as expected.

Proto definition:

.. code-block::

    syntax = "proto3";

    package helloworld;

    // The greeting service definition.
    service Greeter {
      // Sends a greeting
      rpc SayHello (HelloRequest) returns (HelloReply) {}
    }

    // The request message containing the user's name.
    message HelloRequest {
      string name = 1;
    }

    // The response message containing the greetings
    message HelloReply {
      string message = 1;
    }


Service initialization example:


.. code-block:: python

    import grpc

    import aiomisc
    from aiomisc.service.grpc_server import GRPCService


    protos, services = grpc.protos_and_services("hello.proto")


    class Greeter(services.GreeterServicer):
        async def SayHello(self, request, context):
            return protos.HelloReply(message='Hello, %s!' % request.name)


    def main():
        grpc_service = GRPCService(compression=grpc.Compression.Gzip)
        services.add_GreeterServicer_to_server(
            Greeter(), grpc_service,
        )
        grpc_service.add_insecure_port('[::]:0')
        grpc_service.add_insecure_port('[::1]:0')
        grpc_service.add_insecure_port('127.0.0.1:0')
        grpc_service.add_insecure_port('localhost:0')
        grpc_service.add_secure_port('localhost:0', grpc.local_server_credentials())
        grpc_service.add_secure_port('[::]:0', grpc.local_server_credentials())

        with aiomisc.entrypoint(grpc_service) as loop:
            loop.run_forever()


    if __name__ == '__main__':
        main()


To enable reflection for the service you use reflection flag:

.. code-block:: python

    GRPCService(reflection=True)
