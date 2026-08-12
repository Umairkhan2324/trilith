"""Regression tests for the defects fixed alongside multi-tenancy."""

import time

import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.ops import fold_subtask, purge_expired, write_item
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import build_runtime


def make_item(item_id, tier=Tier.SEMANTIC, scope=Scope.TENANT, content="data", expires_s=None):
    ts = Timestamp()
    ts.GetCurrentTime()
    item = ContextItem(
        id=item_id,
        tier=tier,
        scope=scope,
        content=content,
        provenance="tests",
        created_at=ts,
    )
    if expires_s is not None:
        item.expires_at.CopyFrom(Timestamp(seconds=int(expires_s), nanos=0))
    return item


@pytest.fixture
def rt():
    return build_runtime(":memory:")


# --- Bug 1: assemble() raised whenever the episodic tier was unaddressable ---


@pytest.mark.parametrize("requester_scope", ["GLOBAL", "", "SCOPE_UNSPECIFIED", "nonsense"])
def test_assemble_no_longer_raises_on_broad_scopes(rt, requester_scope):
    """The Governor used to propagate EpisodicStore's ValueError/KeyError.

    That made the REST endpoint's own default (`requester_scope="GLOBAL"`)
    a guaranteed 500.
    """
    result = rt.governor.assemble("anything", budget=200, requester_scope=requester_scope)
    assert result.tokens_used == 0
    assert list(result.items) == []


def test_assemble_with_global_scope_returns_global_items(rt):
    write_item(rt, make_item("g", scope=Scope.GLOBAL, content="shared fact"), principal=Principal())
    result = rt.governor.assemble("shared fact", budget=200, requester_scope="GLOBAL")
    assert [i.id for i in result.items] == ["g"]


def test_episodic_store_still_guards_the_legacy_string_api(rt):
    """The v0.1 guard stays in place for callers who pass no principal."""
    with pytest.raises(ValueError):
        rt.episodic.query(scope="")
    with pytest.raises(KeyError):
        rt.episodic.query(scope="GLOBAL")


# --- Bug 2: every assemble scanned the whole tier ---


def test_candidate_cap_bounds_the_scan_and_is_reported(rt):
    p = Principal(tenant_id="acme")
    for n in range(50):
        write_item(rt, make_item(f"i{n}", content=f"fact number {n}"), principal=p)

    rt.governor.max_candidates = 10
    result = rt.governor.assemble("fact number", budget=10_000, principal=p)

    assert len(result.items) <= 10
    # The truncation is surfaced, not silent.
    assert result.candidates_truncated == 40


def test_no_truncation_reported_when_everything_fits(rt):
    p = Principal(tenant_id="acme")
    for n in range(5):
        write_item(rt, make_item(f"i{n}", content=f"fact {n}"), principal=p)

    result = rt.governor.assemble("fact", budget=10_000, principal=p)
    assert result.candidates_truncated == 0


def test_distraction_penalty_is_skipped_above_the_pairwise_limit(rt):
    p = Principal(tenant_id="acme")
    for n in range(20):
        write_item(rt, make_item(f"i{n}", content=f"routing algorithm {n}"), principal=p)

    rt.governor.max_pairwise = 5
    result = rt.governor.assemble("routing algorithm", budget=10_000, principal=p)
    # Still ranks and assembles; it just drops the O(n^2) refinement.
    assert len(result.items) == 20


# --- Bug 3: fold() was unreachable outside in-process Python ---


def test_fold_is_available_through_the_shared_ops_layer(rt):
    p = Principal(tenant_id="acme")
    for n in (1, 2, 3):
        item = make_item(f"step-{n}", tier=Tier.PROCEDURAL, content=f"did thing {n}")
        p.stamp(item)
        rt.procedural.write(item, subtask_id="deploy-1")

    summary, count = fold_subtask(rt, "deploy-1", principal=p)

    assert count == 3
    assert summary.id == "folded-deploy-1"
    assert all(f"did thing {n}" in summary.content for n in (1, 2, 3))

    remaining = rt.backend.query(Tier.PROCEDURAL, tenant_id="acme")
    assert [i.id for i in remaining] == ["folded-deploy-1"]


def test_fold_on_unknown_subtask_reports_nothing_folded(rt):
    summary, count = fold_subtask(rt, "does-not-exist", principal=Principal())
    assert summary is None and count == 0


# --- Bug 4: expired items were hidden but never reaped ---


def test_expired_items_are_physically_deleted(rt):
    p = Principal(tenant_id="acme")
    past = time.time() - 60
    future = time.time() + 3600

    write_item(rt, make_item("old", content="stale", expires_s=past), principal=p)
    write_item(rt, make_item("new", content="fresh", expires_s=future), principal=p)

    assert purge_expired(rt, principal=p) == 1

    rows = rt.backend.query(Tier.SEMANTIC, tenant_id="acme")
    assert [r.id for r in rows] == ["new"]


def test_purge_expired_is_tenant_scoped(rt):
    past = time.time() - 60
    write_item(rt, make_item("a", content="stale", expires_s=past), principal=Principal(tenant_id="acme"))
    write_item(rt, make_item("g", content="stale", expires_s=past), principal=Principal(tenant_id="globex"))

    assert purge_expired(rt, principal=Principal(tenant_id="acme")) == 1
    assert len(rt.backend.query(Tier.SEMANTIC, tenant_id="globex")) == 1


def test_expired_items_are_reaped_on_startup(tmp_path):
    db = str(tmp_path / "reap.db")
    rt = build_runtime(db)
    write_item(
        rt,
        make_item("old", content="stale", expires_s=time.time() - 60),
        principal=Principal(),
    )
    assert len(rt.backend.query(Tier.SEMANTIC, tenant_id="default")) == 1

    reopened = build_runtime(db)
    assert reopened.backend.query(Tier.SEMANTIC, tenant_id="default") == []


# --- Bug 5: the MCP adapter bypassed the shared, thread-safe runtime ---


def test_mcp_adapter_uses_the_shared_runtime():
    import ast
    import pathlib

    source = pathlib.Path("adapters/mcp/server.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }

    assert "build_runtime" in imported
    # It must not hand-roll an unsynchronised backend of its own.
    assert "SQLiteBackend" not in imported
