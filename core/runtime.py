"""Shared runtime wiring for REST, gRPC, and in-process use."""

from __future__ import annotations

from dataclasses import dataclass
import os

from core.episodic import EpisodicStore
from core.governor import Governor
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


def resolve_db_path(db: str | None = None) -> str:
    return db or os.environ.get("TRILITH_DB_PATH", "trilith.db")


def build_runtime(db_path: str | None = None) -> TrilithRuntime:
    path = resolve_db_path(db_path)
    backend = ThreadSafeBackend(SQLiteBackend(path))
    semantic = SemanticStore(backend)
    procedural = ProceduralStore(backend)
    episodic = EpisodicStore(backend)
    governor = Governor(
        semantic_store=semantic,
        procedural_store=procedural,
        episodic_store=episodic,
        policy_engine=PolicyEngine(),
    )
    return TrilithRuntime(
        semantic=semantic,
        procedural=procedural,
        episodic=episodic,
        governor=governor,
        db_path=path,
    )
