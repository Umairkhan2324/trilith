"""Thread-safe wrapper around a store backend (REST + gRPC share one DB)."""

from __future__ import annotations

from threading import Lock
from typing import List, Optional

from core.proto.trilith_pb2 import ContextItem, Scope, Tier


class ThreadSafeBackend:
    def __init__(self, backend):
        self._backend = backend
        self._lock = Lock()

    def save(self, item: ContextItem, subtask_id: Optional[str] = None) -> bool:
        with self._lock:
            return self._backend.save(item, subtask_id=subtask_id)

    def get(self, item_id: str) -> Optional[ContextItem]:
        with self._lock:
            return self._backend.get(item_id)

    def query(
        self,
        tier: Tier,
        scope: Optional[Scope] = None,
        subtask_id: Optional[str] = None,
    ) -> List[ContextItem]:
        with self._lock:
            return self._backend.query(tier, scope=scope, subtask_id=subtask_id)

    def delete(self, item_id: str) -> bool:
        with self._lock:
            return self._backend.delete(item_id)

    def delete_by_scope(self, scope: Scope, tier: Optional[Tier] = None) -> int:
        with self._lock:
            return self._backend.delete_by_scope(scope, tier=tier)
