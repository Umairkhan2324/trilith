"""A v0.1 database must keep working after the multi-tenancy upgrade."""

import sqlite3

from core.identity import DEFAULT_TENANT, Principal
from core.proto.trilith_pb2 import Scope, Tier
from core.runtime import build_runtime
from core.sqlite_backend import SQLiteBackend

# The exact schema shipped in v0.1, before tenant/owner/session existed.
V01_SCHEMA = """
    CREATE TABLE context_items (
        id TEXT PRIMARY KEY,
        tier INTEGER,
        content TEXT,
        scope INTEGER,
        provenance TEXT,
        created_at_sec INTEGER,
        created_at_nanosec INTEGER,
        expires_at_sec INTEGER,
        expires_at_nanosec INTEGER,
        embedding TEXT,
        subtask_id TEXT
    )
"""


def _make_v01_db(path: str):
    conn = sqlite3.connect(path)
    conn.execute(V01_SCHEMA)
    conn.execute(
        "INSERT INTO context_items "
        "(id, tier, content, scope, provenance, created_at_sec, created_at_nanosec, "
        " expires_at_sec, expires_at_nanosec, embedding, subtask_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, NULL)",
        ("legacy-1", int(Tier.SEMANTIC), "Alice prefers Python", int(Scope.USER),
         "v0.1", 1_700_000_000, 0),
    )
    conn.commit()
    conn.close()


def test_old_database_gains_tenancy_columns(tmp_path):
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    backend = SQLiteBackend(db)

    cursor = backend.conn.cursor()
    cursor.execute("PRAGMA table_info(context_items)")
    columns = {row[1] for row in cursor.fetchall()}
    assert {"tenant_id", "owner_id", "session_id"} <= columns


def test_existing_rows_are_backfilled_into_the_default_tenant(tmp_path):
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    backend = SQLiteBackend(db)
    item = backend.get("legacy-1")

    assert item is not None
    assert item.tenant_id == DEFAULT_TENANT
    assert item.owner_id == ""
    assert item.content == "Alice prefers Python"


def test_legacy_data_is_readable_through_the_default_tenant(tmp_path):
    """Migrated rows are USER-scoped but own no owner_id, so they cannot be
    owner-isolated. Any identified caller in the default tenant sees them."""
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    rt = build_runtime(db)
    result = rt.governor.assemble(
        "What does Alice prefer?",
        budget=200,
        principal=Principal(owner_id="alice"),
    )

    assert [i.id for i in result.items] == ["legacy-1"]


def test_anonymous_principal_still_needs_a_scope_for_legacy_rows(tmp_path):
    """A principal with no identity at all is treated exactly like a v0.1 caller."""
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    rt = build_runtime(db)
    anonymous = rt.governor.assemble("Alice", budget=200, principal=Principal())
    assert anonymous.items == []
    assert "Scope mismatch" in anonymous.excluded_items[0].reason


def test_legacy_requester_scope_still_works(tmp_path):
    """v0.1 callers passing a bare scope name keep the behaviour they had."""
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    rt = build_runtime(db)
    result = rt.governor.assemble("Alice", budget=200, requester_scope="USER")
    assert [i.id for i in result.items] == ["legacy-1"]

    # ...and a mismatched scope still excludes the item, with a reason.
    denied = rt.governor.assemble("Alice", budget=200, requester_scope="SESSION")
    assert denied.items == []
    assert "Scope mismatch" in denied.excluded_items[0].reason


def test_migration_is_idempotent(tmp_path):
    db = str(tmp_path / "old.db")
    _make_v01_db(db)

    SQLiteBackend(db)
    backend = SQLiteBackend(db)  # second open must not fail or duplicate columns

    cursor = backend.conn.cursor()
    cursor.execute("PRAGMA table_info(context_items)")
    names = [row[1] for row in cursor.fetchall()]
    assert len(names) == len(set(names))
    assert backend.get("legacy-1") is not None
