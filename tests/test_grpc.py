"""gRPC ContextManager integration tests."""

import grpc
import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from core.grpc_server import create_grpc_server
from core.proto import trilith_pb2, trilith_pb2_grpc
from core.proto.trilith_pb2 import ContextItem, Principal, Scope, Tier
from core.runtime import build_runtime


def _item(item_id: str, content: str, tier=Tier.SEMANTIC, scope=Scope.USER) -> ContextItem:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ContextItem(
        id=item_id,
        tier=tier,
        scope=scope,
        content=content,
        provenance="test_grpc",
        created_at=ts,
    )


@pytest.fixture
def server():
    rt = build_runtime(":memory:")
    srv, port = create_grpc_server(rt, "127.0.0.1", 0)
    srv.start()
    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    try:
        yield rt, trilith_pb2_grpc.ContextManagerStub(channel)
    finally:
        srv.stop(grace=0)


def _meta(key: str):
    return (("authorization", f"Bearer {key}"),)


def test_grpc_write_assemble_forget(server):
    _, stub = server

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


def test_grpc_tenant_isolation(server):
    _, stub = server
    acme = Principal(tenant_id="acme")
    globex = Principal(tenant_id="globex")

    stub.Write(
        trilith_pb2.WriteRequest(
            item=_item("a1", "acme roadmap", scope=Scope.TENANT), principal=acme
        )
    )
    stub.Write(
        trilith_pb2.WriteRequest(
            item=_item("g1", "globex roadmap", scope=Scope.TENANT), principal=globex
        )
    )

    seen = stub.Assemble(
        trilith_pb2.AssembleRequest(
            task_description="roadmap", budget_tokens=500, principal=acme
        )
    )
    assert [i.id for i in seen.items] == ["a1"]


def test_grpc_rejects_calls_without_a_key_once_auth_is_on(server):
    rt, stub = server
    rt.keys.create(tenant_id="acme")

    with pytest.raises(grpc.RpcError) as exc:
        stub.Assemble(trilith_pb2.AssembleRequest(task_description="x", budget_tokens=100))
    assert exc.value.code() == grpc.StatusCode.UNAUTHENTICATED


def test_grpc_key_metadata_pins_the_tenant(server):
    rt, stub = server
    raw, _ = rt.keys.create(tenant_id="acme")

    # Ask to write into globex; the key forces acme.
    stub.Write(
        trilith_pb2.WriteRequest(
            item=_item("a1", "acme secret", scope=Scope.TENANT),
            principal=Principal(tenant_id="globex"),
        ),
        metadata=_meta(raw),
    )

    globex_raw, _ = rt.keys.create(tenant_id="globex")
    seen = stub.Assemble(
        trilith_pb2.AssembleRequest(
            task_description="acme secret",
            budget_tokens=500,
            principal=Principal(tenant_id="acme"),
        ),
        metadata=_meta(globex_raw),
    )
    assert list(seen.items) == []


def test_grpc_fold(server):
    rt, stub = server
    for n in (1, 2, 3):
        item = _item(f"step-{n}", f"did thing {n}", tier=Tier.PROCEDURAL, scope=Scope.TENANT)
        item.tenant_id = "default"
        rt.procedural.write(item, subtask_id="deploy-7")

    resp = stub.Fold(trilith_pb2.FoldRequest(subtask_id="deploy-7"))
    assert resp.success is True
    assert resp.folded_count == 3
    assert resp.item.id == "folded-deploy-7"


def test_grpc_fold_unknown_subtask(server):
    _, stub = server
    resp = stub.Fold(trilith_pb2.FoldRequest(subtask_id="nope"))
    assert resp.success is False
    assert resp.folded_count == 0


def test_grpc_purge_expired(server):
    import time

    rt, stub = server
    item = _item("old", "stale", scope=Scope.TENANT)
    item.tenant_id = "default"
    item.expires_at.CopyFrom(Timestamp(seconds=int(time.time() - 60)))
    rt.semantic.write(item)

    resp = stub.PurgeExpired(trilith_pb2.PurgeExpiredRequest())
    assert resp.success is True
    assert resp.deleted_count == 1
