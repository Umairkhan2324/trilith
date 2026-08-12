"""Shared runtime wiring for REST, gRPC, and in-process use."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from core.auth import ApiKeyStore, AuthEnforcer
from core.episodic import EpisodicStore
from core.governor import Governor
from core.identity import Principal
from core.privacy import PolicyEngine
from core.procedural import ProceduralStore
from core.semantic import SemanticStore
from core.sqlite_backend import SQLiteBackend
from core.threadsafe_backend import ThreadSafeBackend


@dataclass
class TrilithRuntime:
    semantic: SemanticStore
    procedural: ProceduralStore
    episodic: EpisodicStore
    governor: Governor
    db_path: str
    backend: ThreadSafeBackend
    auth: AuthEnforcer

    @property
    def keys(self) -> ApiKeyStore:
        return self.auth.store

    def principal(
        self,
        tenant_id: str = "",
        owner_id: str = "",
        session_id: str = "",
    ) -> Principal:
        """Build a Principal directly — the in-process equivalent of an API key."""
        return Principal(tenant_id=tenant_id, owner_id=owner_id, session_id=session_id)


def resolve_db_path(db: str | None = None) -> str:
    return db or os.environ.get("TRILITH_DB_PATH", "trilith.db")


def build_runtime(
    db_path: str | None = None,
    require_auth: Optional[bool] = None,
    max_candidates: int = 500,
) -> TrilithRuntime:
    path = resolve_db_path(db_path)
    sqlite_backend = SQLiteBackend(path)
    backend = ThreadSafeBackend(sqlite_backend)

    # Keys live in the same database file, so one volume carries both the
    # context and the credentials that scope it.
    key_store = ApiKeyStore(sqlite_backend.conn)

    semantic = SemanticStore(backend)
    procedural = ProceduralStore(backend)
    episodic = EpisodicStore(backend)
    governor = Governor(
        semantic_store=semantic,
        procedural_store=procedural,
        episodic_store=episodic,
        policy_engine=PolicyEngine(),
        max_candidates=max_candidates,
    )

    # Reap anything already past its TTL, so expired rows do not accumulate
    # across restarts and slow down every later scan.
    backend.purge_expired()

    return TrilithRuntime(
        semantic=semantic,
        procedural=procedural,
        episodic=episodic,
        governor=governor,
        db_path=path,
        backend=backend,
        auth=AuthEnforcer(key_store, require_auth=require_auth),
    )
