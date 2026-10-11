"""Shared runtime wiring for REST, gRPC, and in-process use."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from core.audit import AuditLog
from core.auth import ApiKeyStore, AuthEnforcer
from core.episodic import EpisodicStore
from core.events import EventLog
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
    audit: AuditLog
    # Recent operations, for consoles. In-memory and bounded — see core.events.
    events: EventLog = field(default_factory=EventLog)

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


# The score an item must beat to be assembled into a prompt. See Governor.
DEFAULT_MIN_SCORE = 0.0

# Spellings that mean "no floor". `-inf` is the honest value but a leading dash
# is awkward to pass: argparse reads `--min-score -inf` as a missing argument
# followed by an unknown flag. `off` is what an operator can actually type.
_FLOOR_DISABLED = frozenset({"off", "none", "disabled", "-inf", "-infinity"})


def parse_min_score(raw: str) -> float:
    """Read a relevance floor from a flag value or an environment variable."""
    value = raw.strip().lower()
    if value in _FLOOR_DISABLED:
        return float("-inf")
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(
            f"min score must be a number, or one of {sorted(_FLOOR_DISABLED)}; got {raw!r}"
        ) from exc


def resolve_min_score(min_score: Optional[float] = None) -> float:
    """The relevance floor, from the argument, the environment, or the default.

    Disabling it opts back into pre-0.3 behaviour, where the budget was the only
    thing standing between a stored item and the prompt.
    """
    if min_score is not None:
        return float(min_score)

    raw = os.environ.get("TRILITH_MIN_SCORE", "").strip()
    if not raw:
        return DEFAULT_MIN_SCORE
    try:
        return parse_min_score(raw)
    except ValueError as exc:
        raise ValueError(f"TRILITH_MIN_SCORE is invalid: {exc}") from exc


def build_runtime(
    db_path: str | None = None,
    require_auth: Optional[bool] = None,
    max_candidates: int = 500,
    min_score: Optional[float] = None,
) -> TrilithRuntime:
    path = resolve_db_path(db_path)
    sqlite_backend = SQLiteBackend(path)
    backend = ThreadSafeBackend(sqlite_backend)

    # Keys live in the same database file, so one volume carries both the
    # context and the credentials that scope it.
    key_store = ApiKeyStore(sqlite_backend.conn, lock=backend._lock)

    semantic = SemanticStore(backend)
    procedural = ProceduralStore(backend)
    episodic = EpisodicStore(backend)
    governor = Governor(
        semantic_store=semantic,
        procedural_store=procedural,
        episodic_store=episodic,
        policy_engine=PolicyEngine(),
        max_candidates=max_candidates,
        min_score=resolve_min_score(min_score),
    )

    # Reap anything already past its TTL, so expired rows do not accumulate
    # across restarts and slow down every later scan.
    backend.purge_expired()

    audit = AuditLog(backend)
    governor.audit = audit
    return TrilithRuntime(
        semantic=semantic,
        procedural=procedural,
        episodic=episodic,
        governor=governor,
        db_path=path,
        backend=backend,
        auth=AuthEnforcer(key_store, require_auth=require_auth),
        audit=audit,
    )
