import inspect
import json

import pytest
from fastapi.testclient import TestClient

from core.identity import Principal
from core.ops import assemble_context, fold_subtask, forget_scope, write_item
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.rest_app import create_rest_app
from core.runtime import build_runtime


def item(id="x", content="quartz evidence", tenant="a", **kwargs):
    return ContextItem(
        id=id,
        content=content,
        tenant_id=tenant,
        tier=Tier.SEMANTIC,
        scope=kwargs.pop("scope", Scope.TENANT),
        **kwargs,
    )


def test_same_id_isolated_and_persistent(tmp_path):
    path = str(tmp_path / "keys.db")
    rt = build_runtime(path)
    for tenant in ("a", "b"):
        rt.semantic.write(item(tenant=tenant, content=tenant))
    rt = build_runtime(path)
    assert rt.backend.get("x", "a").content == "a"
    assert rt.backend.get("x", "b").content == "b"
    rt.backend.delete("x", "a")
    assert rt.backend.get("x", "b") is not None


def test_publisher_and_owner_write_boundaries():
    rt = build_runtime(":memory:")
    assert not write_item(rt, item(scope=Scope.GLOBAL), Principal("a")).success
    assert write_item(
        rt, item(scope=Scope.GLOBAL), Principal("a", capabilities=("publish_global",))
    ).success
    assert not write_item(rt, item(), Principal("a")).success
    rt.semantic.write(item(id="private", scope=Scope.USER, owner_id="bob"))
    assert not write_item(
        rt, item(id="private", scope=Scope.USER, owner_id="alice"), Principal("a", "alice")
    ).success


def test_credentials_pin_identity_and_admin_is_explicit():
    rt = build_runtime(":memory:")
    key, _ = rt.keys.create("a", owner_id="alice", session_id="s1")
    p = rt.auth.resolve(key, tenant_id="b", owner_id="bob", session_id="s2")
    assert (p.tenant_id, p.owner_id, p.session_id) == ("a", "alice", "s1")
    client = TestClient(create_rest_app(rt))
    headers = {"Authorization": "Bearer " + key}
    for path in ("/v1/items", "/v1/dashboard", "/v1/events", "/v1/subtasks"):
        assert client.get(path, headers=headers).status_code == 403
    admin, _ = rt.keys.create("a", capabilities=("tenant_admin",))
    assert client.get("/v1/items", headers={"Authorization": admin}).status_code == 200


def test_old_evidence_retrieved_and_private_data_cannot_crowd_it_out():
    rt = build_runtime(":memory:", max_candidates=1)
    rt.semantic.write(item(id="old"))
    for k in range(10):
        x = item(id=str(k), content="irrelevant bananas")
        x.created_at.seconds = k + 10
        rt.semantic.write(x)
        rt.semantic.write(
            item(id="secret" + str(k), content="quartz evidence", scope=Scope.USER, owner_id="bob")
        )
    result = rt.governor.assemble("quartz evidence", 100, principal=Principal("a", "alice"))
    assert [i.id for i in result.items] == ["old"]
    assert "secret" not in str(result)


@pytest.mark.parametrize(
    "query,content",
    [
        ("数据库", "数据库连接失败"),
        ("یادداشت", "یادداشت محفوظ ہے"),
        ("mémoire", "mémoire persistante"),
        ("ذاكرة", "ذاكرة الوكيل"),
    ],
)
def test_multiscript_retrieval(query, content):
    rt = build_runtime(":memory:")
    rt.semantic.write(item(content=content))
    result = rt.governor.assemble(query, 200, principal=Principal("a"))
    assert [i.id for i in result.items] == ["x"]
    assert result.tokens_used == len(content.encode("utf8"))


def test_fold_preserves_sources_and_privacy_tuple():
    rt = build_runtime(":memory:")
    for owner in ("alice", "bob"):
        x = item(
            id=owner,
            owner_id=owner,
            session_id="s",
            scope=Scope.USER,
            content=json.dumps({"strategy": "retry with backoff", "outcome": "recovered"}),
        )
        rt.procedural.write(x, subtask_id="task")
    summary, count = fold_subtask(rt, "task", Principal("a", "alice", "s"))
    assert count == 1
    assert json.loads(summary.content)["outcome"] == "recovered"
    assert "bob" not in summary.content
    assert rt.backend.get("alice", "a") is not None
    assert rt.backend.get("bob", "a") is not None


def test_audit_durable_content_free_and_erasable(tmp_path):
    path = str(tmp_path / "audit.db")
    rt = build_runtime(path)
    p = Principal("a", "alice", capabilities=("tenant_admin",))
    write_item(rt, item(content="quartz SECRET", scope=Scope.USER, owner_id="alice"), p)
    assemble_context(rt, "quartz", 100, p)
    rt = build_runtime(path)
    rows = rt.audit.read(p)
    assert rows and "SECRET" not in json.dumps(rows)
    forget_scope(rt, "USER", p)
    assert all(row["operation"] == "forget" for row in rt.audit.read(p))


def test_transaction_rollback():
    rt = build_runtime(":memory:")
    with pytest.raises(RuntimeError):
        with rt.backend.transaction():
            rt.semantic.write(item())
            raise RuntimeError("injected failure")
    assert rt.backend.get("x", "a") is None


def test_mcp_identity_not_in_tool_schema(monkeypatch):
    monkeypatch.setenv("TRILITH_DB_PATH", ":memory:")
    from adapters.mcp import server

    for fn in (
        server.write_context,
        server.assemble_context,
        server.fold_procedural,
        server.forget,
        server.forget_scope_tool,
        server.purge_expired_items,
    ):
        assert not {"tenant_id", "owner_id", "session_id"} & set(inspect.signature(fn).parameters)


def test_erasing_a_source_invalidates_derived_memory():
    rt = build_runtime(":memory:")
    p = Principal("a", "alice")
    x = item(scope=Scope.USER, owner_id="alice")
    rt.procedural.write(x, subtask_id="t")
    summary, _ = fold_subtask(rt, "t", p)
    assert rt.backend.get(summary.id, "a") is not None
    rt.backend.delete("x", "a")
    assert rt.backend.get(summary.id, "a") is None


def test_hybrid_retrieval_and_embedding_validation():
    from core.retrieval import HybridScorer

    scorer = HybridScorer(lambda _: [1.0, 0.0])
    scores = scorer.score([item(content="different language", embedding=[1.0, 0.0])], "query")
    assert scores[0] > 0
    with pytest.raises(ValueError, match="dimension"):
        scorer.score([item(embedding=[1.0, 0.0, 0.0])], "query")


def test_budget_packer_can_prefer_complementary_small_items():
    from core.retrieval import pack

    candidates = [
        item(id="big", content="alpha beta long"),
        item(id="a", content="alpha"),
        item(id="b", content="beta"),
    ]
    costs = {"big": 10, "a": 5, "b": 5}
    chosen = pack(candidates, [0.9, 0.8, 0.8], "alpha beta", 10, lambda i: costs[i.id])
    assert set(chosen) == {1, 2}


def test_gateways_deny_tenant_forget_for_unprivileged_key():
    rt = build_runtime(":memory:")
    key, _ = rt.keys.create("a", owner_id="alice")
    client = TestClient(create_rest_app(rt))
    assert (
        client.post(
            "/v1/forget", json={"scope": "TENANT"}, headers={"Authorization": key}
        ).status_code
        == 403
    )
