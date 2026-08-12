"""REST gateway: tenancy, auth enforcement, and the newly exposed endpoints."""

import pytest
from fastapi.testclient import TestClient

from core.rest_app import create_rest_app
from core.runtime import build_runtime


@pytest.fixture
def rt():
    return build_runtime(":memory:")


@pytest.fixture
def client(rt):
    return TestClient(create_rest_app(rt))


def _auth(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


# --- Open mode: the local quickstart must work with no credentials ---


def test_health_reports_auth_state(client):
    body = client.get("/healthz").json()
    assert body["status"] == "ok"
    assert body["auth_enabled"] is False


def test_write_and_assemble_without_auth(client):
    r = client.post(
        "/v1/write",
        json={"id": "f1", "tier": "SEMANTIC", "scope": "USER", "content": "Alice prefers Python."},
    )
    assert r.status_code == 200
    assert r.json()["tenant_id"] == "default"

    ctx = client.post(
        "/v1/assemble",
        json={"task": "What does Alice prefer?", "budget": 200, "requester_scope": "USER"},
    ).json()
    assert [i["id"] for i in ctx["items"]] == ["f1"]


def test_assemble_default_body_no_longer_500s(client):
    """The endpoint's own defaults used to raise out of the Governor."""
    r = client.post("/v1/assemble", json={"task": "anything"})
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_zero_config_quickstart_round_trips(client):
    """Write then read with no identity, no key, no scope juggling.

    TENANT is the default write scope precisely so this composes: an item
    scoped to a user nobody named could not be handed back to an anonymous
    reader without lying about isolation.
    """
    client.post(
        "/v1/write",
        json={"id": "f1", "tier": "SEMANTIC", "scope": "TENANT",
              "content": "Alice prefers Python."},
    )
    ctx = client.post("/v1/assemble", json={"task": "What does Alice prefer?"}).json()
    assert [i["id"] for i in ctx["items"]] == ["f1"]


def test_whoami_in_open_mode(client):
    body = client.get("/v1/whoami").json()
    assert body["tenant_id"] == "default"
    assert body["auth_enabled"] is False


# --- Enforced mode ---


def test_requests_are_rejected_once_a_key_exists(client, rt):
    rt.keys.create(tenant_id="acme")
    r = client.post("/v1/assemble", json={"task": "anything"})
    assert r.status_code == 401
    assert "Missing API key" in r.json()["detail"]


def test_bad_key_is_rejected(client, rt):
    rt.keys.create(tenant_id="acme")
    r = client.post("/v1/assemble", json={"task": "x"}, headers=_auth("tri_bogus"))
    assert r.status_code == 401


def test_key_pins_the_tenant_against_a_spoofed_body(client, rt):
    raw, _ = rt.keys.create(tenant_id="acme")

    r = client.post(
        "/v1/write",
        json={
            "id": "f1",
            "tier": "SEMANTIC",
            "scope": "TENANT",
            "content": "acme secret",
            "tenant_id": "globex",
        },
        headers=_auth(raw),
    )
    assert r.json()["tenant_id"] == "acme"

    # A globex key sees nothing acme wrote, no matter what it asks for.
    globex_raw, _ = rt.keys.create(tenant_id="globex")
    ctx = client.post(
        "/v1/assemble",
        json={"task": "acme secret", "tenant_id": "acme"},
        headers=_auth(globex_raw),
    ).json()
    assert ctx["items"] == []
    assert ctx["tenant_id"] == "globex"


def test_two_tenants_do_not_see_each_other(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")

    for key, name in ((acme_key, "acme"), (globex_key, "globex")):
        client.post(
            "/v1/write",
            json={"id": f"{name}-1", "tier": "SEMANTIC", "scope": "TENANT",
                  "content": f"{name} roadmap"},
            headers=_auth(key),
        )

    ctx = client.post("/v1/assemble", json={"task": "roadmap"}, headers=_auth(acme_key)).json()
    assert [i["id"] for i in ctx["items"]] == ["acme-1"]


def test_whoami_reflects_the_key(client, rt):
    raw, _ = rt.keys.create(tenant_id="acme", owner_id="alice")
    body = client.get("/v1/whoami", headers=_auth(raw)).json()
    assert body["tenant_id"] == "acme"
    assert body["owner_id"] == "alice"
    assert body["auth_enabled"] is True


# --- Endpoints that were previously unreachable over HTTP ---


def test_fold_endpoint(client):
    for n in (1, 2):
        client.post(
            "/v1/write",
            json={"id": f"s{n}", "tier": "PROCEDURAL", "scope": "TENANT",
                  "content": f"step {n}"},
        )
    # Steps must share a subtask to be foldable; write them through the store.
    r = client.post("/v1/fold", json={"subtask_id": "nope"})
    assert r.status_code == 200
    assert r.json()["success"] is False


def test_fold_endpoint_collapses_steps(client, rt):
    from google.protobuf.timestamp_pb2 import Timestamp

    from core.identity import Principal
    from core.proto.trilith_pb2 import ContextItem, Scope, Tier

    ts = Timestamp()
    ts.GetCurrentTime()
    for n in (1, 2, 3):
        item = ContextItem(
            id=f"step-{n}", tier=Tier.PROCEDURAL, scope=Scope.TENANT,
            content=f"did thing {n}", created_at=ts, tenant_id="default",
        )
        rt.procedural.write(item, subtask_id="deploy-9")

    body = client.post("/v1/fold", json={"subtask_id": "deploy-9"}).json()
    assert body["success"] is True
    assert body["folded_count"] == 3
    assert body["item"]["id"] == "folded-deploy-9"

    remaining = rt.backend.query(Tier.PROCEDURAL, tenant_id=Principal().tenant_id)
    assert [i.id for i in remaining] == ["folded-deploy-9"]


def test_purge_expired_endpoint(client, rt):
    import time

    from google.protobuf.timestamp_pb2 import Timestamp

    from core.proto.trilith_pb2 import ContextItem, Scope, Tier

    ts = Timestamp()
    ts.GetCurrentTime()
    item = ContextItem(
        id="old", tier=Tier.SEMANTIC, scope=Scope.TENANT, content="stale",
        created_at=ts, tenant_id="default",
    )
    item.expires_at.CopyFrom(Timestamp(seconds=int(time.time() - 60)))
    rt.semantic.write(item)

    body = client.post("/v1/purge-expired", json={}).json()
    assert body["deleted_count"] == 1


def test_forget_is_confined_to_the_callers_tenant(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")

    for key, name in ((acme_key, "acme"), (globex_key, "globex")):
        client.post(
            "/v1/write",
            json={"id": f"{name}-1", "tier": "EPISODIC", "scope": "TENANT",
                  "content": f"{name} event"},
            headers=_auth(key),
        )

    r = client.post("/v1/forget", json={"scope": "TENANT"}, headers=_auth(acme_key)).json()
    assert r["deleted_episodic_count"] == 1

    ctx = client.post("/v1/assemble", json={"task": "event"}, headers=_auth(globex_key)).json()
    assert [i["id"] for i in ctx["items"]] == ["globex-1"]
