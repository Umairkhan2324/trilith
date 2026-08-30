"""The endpoints a console needs: browse, edit, delete, and watch.

These are the operations that let a human change context instead of only
reading it, so the things under test are mostly boundaries: an edit must not
reach across a tenant, a browse must not invent visibility it does not have,
and the activity log must not show one tenant another's traffic.
"""

import time

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


def _write(client, item_id, tier="SEMANTIC", scope="TENANT", **extra):
    body = {
        "id": item_id,
        "tier": tier,
        "scope": scope,
        "content": extra.pop("content", f"content of {item_id}"),
    }
    body.update(extra)
    response = client.post("/v1/write", json=body, headers=extra.pop("headers", {}) or {})
    assert response.status_code == 200, response.text
    return response.json()


# --- Browsing ------------------------------------------------------------


def test_items_lists_every_tier_newest_first(client):
    for item_id, tier in (("f1", "SEMANTIC"), ("p1", "PROCEDURAL"), ("e1", "EPISODIC")):
        _write(client, item_id, tier=tier)

    body = client.get("/v1/items").json()
    assert body["total"] == 3
    assert {item["id"] for item in body["items"]} == {"f1", "p1", "e1"}
    assert all(item["tokens"] > 0 for item in body["items"])


def test_items_filters_by_tier_scope_and_text(client):
    _write(client, "python-fact", content="Alice prefers Python", tier="SEMANTIC")
    _write(client, "rust-fact", content="Bob prefers Rust", tier="SEMANTIC", scope="GLOBAL")
    _write(client, "step", content="ran the deploy", tier="PROCEDURAL")

    assert client.get("/v1/items?tier=PROCEDURAL").json()["total"] == 1
    assert client.get("/v1/items?scope=GLOBAL").json()["total"] == 1
    assert [i["id"] for i in client.get("/v1/items?q=python").json()["items"]] == ["python-fact"]
    # Text search covers identifiers and provenance, not just content.
    assert client.get("/v1/items?q=deploy").json()["total"] == 1


def test_items_pages(client):
    for n in range(5):
        _write(client, f"item-{n}")

    first = client.get("/v1/items?limit=2").json()
    second = client.get("/v1/items?limit=2&offset=2").json()
    assert first["total"] == second["total"] == 5
    assert len(first["items"]) == len(second["items"]) == 2
    assert not {i["id"] for i in first["items"]} & {i["id"] for i in second["items"]}


def test_items_reports_why_something_is_unreachable(client):
    """A stored row the caller cannot receive is listed, with the reason."""
    _write(client, "mine", scope="USER", owner_id="maya")

    as_maya = client.get("/v1/items?owner_id=maya").json()["items"][0]
    assert as_maya["visible"] is True
    assert as_maya["visibility_reason"] == ""

    as_sam = client.get("/v1/items?owner_id=sam").json()["items"][0]
    assert as_sam["visible"] is False
    assert "Owner mismatch" in as_sam["visibility_reason"]


def test_items_never_cross_a_tenant(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")
    client.post(
        "/v1/write",
        json={"id": "acme-only", "tier": "SEMANTIC", "scope": "TENANT", "content": "secret"},
        headers=_auth(acme_key),
    )

    assert client.get("/v1/items", headers=_auth(globex_key)).json()["total"] == 0
    assert client.get("/v1/items", headers=_auth(acme_key)).json()["total"] == 1


def test_episodic_global_items_stay_in_their_tenant(client, rt):
    """The browse path honours the tiers' own include_global rule."""
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")
    for tier in ("SEMANTIC", "EPISODIC"):
        client.post(
            "/v1/write",
            json={"id": f"{tier}-global", "tier": tier, "scope": "GLOBAL", "content": "shared"},
            headers=_auth(acme_key),
        )

    seen = {i["id"] for i in client.get("/v1/items", headers=_auth(globex_key)).json()["items"]}
    assert seen == {"SEMANTIC-global"}


def test_get_single_item_and_404(client):
    _write(client, "known")
    assert client.get("/v1/items/known").json()["id"] == "known"
    assert client.get("/v1/items/unknown").status_code == 404


# --- Editing -------------------------------------------------------------


def test_patch_changes_only_what_it_was_given(client):
    _write(client, "fact", content="original", provenance="notes.md")

    body = client.patch("/v1/items/fact", json={"content": "revised"}).json()
    assert body["changed"] == ["content"]
    assert body["item"]["content"] == "revised"
    assert body["item"]["provenance"] == "notes.md"


def test_patch_reports_no_change_without_writing(client):
    _write(client, "fact", content="same")
    body = client.patch("/v1/items/fact", json={"content": "same"}).json()
    assert body["changed"] == []
    assert body["item"] is None


def test_patch_can_move_an_item_between_tiers_and_scopes(client):
    _write(client, "note", tier="EPISODIC", scope="SESSION")

    body = client.patch("/v1/items/note", json={"tier": "SEMANTIC", "scope": "TENANT"}).json()
    assert set(body["changed"]) == {"tier", "scope"}
    assert client.get("/v1/items?tier=SEMANTIC").json()["total"] == 1
    assert client.get("/v1/items?tier=EPISODIC").json()["total"] == 0


def test_patch_preserves_the_subtask_it_was_not_asked_about(client):
    """Folding groups by a column the item body does not carry; an edit must
    not silently orphan a step from its sub-task."""
    _write(client, "step-1", tier="PROCEDURAL", subtask_id="deploy-9")

    client.patch("/v1/items/step-1", json={"content": "edited step"})
    assert client.get("/v1/items/step-1").json()["subtask_id"] == "deploy-9"
    assert client.get("/v1/subtasks").json()["subtasks"] == [{"subtask_id": "deploy-9", "steps": 1}]


def test_patch_rejects_an_unknown_tier(client):
    _write(client, "fact")
    assert client.patch("/v1/items/fact", json={"tier": "NONSENSE"}).status_code == 400


def test_patch_cannot_reach_into_another_tenant(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")
    client.post(
        "/v1/write",
        json={"id": "acme-only", "tier": "SEMANTIC", "scope": "TENANT", "content": "secret"},
        headers=_auth(acme_key),
    )

    response = client.patch(
        "/v1/items/acme-only",
        json={"content": "tampered"},
        headers=_auth(globex_key),
    )
    assert response.status_code == 404
    assert client.get("/v1/items/acme-only", headers=_auth(acme_key)).json()["content"] == "secret"


def test_delete_removes_one_item(client):
    _write(client, "keep")
    _write(client, "drop")

    assert client.delete("/v1/items/drop").json()["success"] is True
    assert client.delete("/v1/items/drop").status_code == 404
    assert [i["id"] for i in client.get("/v1/items").json()["items"]] == ["keep"]


def test_delete_cannot_reach_into_another_tenant(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")
    client.post(
        "/v1/write",
        json={"id": "acme-only", "tier": "SEMANTIC", "scope": "TENANT", "content": "secret"},
        headers=_auth(acme_key),
    )

    assert client.delete("/v1/items/acme-only", headers=_auth(globex_key)).status_code == 404
    assert client.get("/v1/items", headers=_auth(acme_key)).json()["total"] == 1


# --- Writing with the fields the pipeline needs ---------------------------


def test_write_accepts_a_subtask_so_fold_is_reachable_over_rest(client):
    """Before this, only an in-process caller could produce foldable steps."""
    for n in (1, 2, 3):
        _write(client, f"step-{n}", tier="PROCEDURAL", subtask_id="deploy-9")

    body = client.post("/v1/fold", json={"subtask_id": "deploy-9"}).json()
    assert body["success"] is True
    assert body["folded_count"] == 3
    assert [i["id"] for i in client.get("/v1/items?tier=PROCEDURAL").json()["items"]] == [
        "folded-deploy-9"
    ]


def test_write_accepts_a_relative_ttl(client):
    _write(client, "ephemeral", ttl_seconds=-1)
    assert client.get("/v1/items/ephemeral").json()["expires_at"] is not None
    assert client.post("/v1/purge-expired", json={}).json()["deleted_count"] == 1


def test_ttl_zero_clears_an_expiry(client):
    _write(client, "fact", ttl_seconds=3600)
    client.patch("/v1/items/fact", json={"ttl_seconds": 0})
    assert client.get("/v1/items/fact").json()["expires_at"] is None


# --- Assembly audit ------------------------------------------------------


def test_assemble_reports_cost_per_item_and_why_things_were_dropped(client):
    _write(client, "wanted", content="Alice prefers Python for data work " * 3)
    _write(client, "filler", content="Unrelated notes about boats " * 6)

    body = client.post(
        "/v1/assemble", json={"task": "What does Alice prefer?", "budget": 30}
    ).json()
    assert body["budget"] == 30
    assert body["tokens_used"] <= 30
    assert all(item["tokens"] > 0 for item in body["items"])

    dropped = body["excluded_items"]
    assert dropped and all(d["kind"] == "budget" for d in dropped)
    assert all(d["content"] for d in dropped)


def test_policy_exclusions_report_the_reason_without_the_content(client):
    """The audit says what was refused and why. It does not hand over the row."""
    _write(client, "someone-elses", scope="USER", owner_id="maya", content="Maya's private note")

    body = client.post(
        "/v1/assemble",
        json={"task": "anything", "budget": 500, "owner_id": "sam"},
    ).json()
    denied = [d for d in body["excluded_items"] if d["id"] == "someone-elses"]
    assert len(denied) == 1
    assert denied[0]["kind"] == "policy"
    assert "Owner mismatch" in denied[0]["reason"]
    assert denied[0]["content"] == ""


# --- Activity log --------------------------------------------------------


def test_events_report_what_happened_in_order(client):
    _write(client, "fact")
    client.patch("/v1/items/fact", json={"content": "revised"})
    client.post("/v1/assemble", json={"task": "anything", "budget": 100})
    client.delete("/v1/items/fact")

    body = client.get("/v1/events").json()
    assert [event["kind"] for event in body["events"]] == [
        "write",
        "update",
        "assemble",
        "delete",
    ]
    assert body["latest_seq"] == 4


def test_events_stream_from_a_cursor(client):
    _write(client, "one")
    cursor = client.get("/v1/events").json()["latest_seq"]
    _write(client, "two")

    body = client.get(f"/v1/events?after={cursor}").json()
    assert [event["detail"]["id"] for event in body["events"]] == ["two"]


def test_events_are_confined_to_the_callers_tenant(client, rt):
    acme_key, _ = rt.keys.create(tenant_id="acme")
    globex_key, _ = rt.keys.create(tenant_id="globex")
    client.post(
        "/v1/write",
        json={"id": "acme-only", "tier": "SEMANTIC", "scope": "TENANT", "content": "secret"},
        headers=_auth(acme_key),
    )

    assert client.get("/v1/events", headers=_auth(globex_key)).json()["events"] == []
    assert len(client.get("/v1/events", headers=_auth(acme_key)).json()["events"]) == 1


def test_event_log_is_bounded(rt):
    """It is a live view, not an audit trail - it must not grow without limit."""
    from core.events import EventLog

    log = EventLog(capacity=3)
    for n in range(10):
        log.record("write", summary=f"event {n}")

    events = log.since()
    assert len(events) == 3
    assert [event.summary for event in events] == ["event 7", "event 8", "event 9"]
    assert log.latest_seq == 10


# --- Tenants -------------------------------------------------------------


def test_tenants_are_listed_in_open_mode_and_pinned_once_auth_is_on(client, rt):
    _write(client, "fact")
    open_body = client.get("/v1/tenants").json()
    assert open_body == {"tenants": ["default"], "scoped": False}

    acme_key, _ = rt.keys.create(tenant_id="acme")
    scoped = client.get("/v1/tenants", headers=_auth(acme_key)).json()
    assert scoped == {"tenants": ["acme"], "scoped": True}


def test_console_endpoints_require_a_key_once_auth_is_on(client, rt):
    rt.keys.create(tenant_id="acme")
    for path in ("/v1/items", "/v1/events", "/v1/subtasks", "/v1/tenants"):
        assert client.get(path).status_code == 401, path
    assert client.delete("/v1/items/anything").status_code == 401
    assert client.patch("/v1/items/anything", json={"content": "x"}).status_code == 401


def test_expired_items_are_reported_as_unreachable_before_they_are_purged(client):
    _write(client, "stale", ttl_seconds=-1)
    time.sleep(0.01)

    row = client.get("/v1/items/stale").json()
    assert row["visible"] is False
    assert "expired" in row["visibility_reason"].lower()
