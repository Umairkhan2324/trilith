"""gRPC ContextManager integration tests."""

from google.protobuf.timestamp_pb2 import Timestamp

from core.grpc_server import create_grpc_server
from core.proto import trilith_pb2, trilith_pb2_grpc
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import build_runtime
import grpc


def _item(item_id: str, content: str) -> ContextItem:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ContextItem(
        id=item_id,
        tier=Tier.SEMANTIC,
        scope=Scope.USER,
        content=content,
        provenance="test_grpc",
        created_at=ts,
    )


def test_grpc_write_assemble_forget():
    rt = build_runtime(":memory:")
    server, port = create_grpc_server(rt, "127.0.0.1", 0)
    server.start()
    try:
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = trilith_pb2_grpc.ContextManagerStub(channel)

        ack = stub.Write(trilith_pb2.WriteRequest(item=_item("g1", "Alice uses Python")))
        assert ack.success is True

        assembled = stub.Assemble(
            trilith_pb2.AssembleRequest(
                task_description="What language does Alice use?",
                budget_tokens=200,
                requester_scope="USER",
            )
        )
        assert assembled.tokens_used > 0
        assert any(i.id == "g1" for i in assembled.items)

        forget = stub.Forget(trilith_pb2.ForgetRequest(scope="USER"))
        assert forget.success is True

        after = stub.Assemble(
            trilith_pb2.AssembleRequest(
                task_description="What language does Alice use?",
                budget_tokens=200,
                requester_scope="USER",
            )
        )
        assert len(after.items) == 0
    finally:
        server.stop(grace=0)
