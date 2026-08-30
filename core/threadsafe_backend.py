"""Thread-safe wrapper around a store backend (REST + gRPC share one DB)."""

from __future__ import annotations

from threading import Lock
from typing import List, Optional, Sequence, Tuple

from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.sqlite_backend import StoredItem


class ThreadSafeBackend:
    def __init__(self, backend):
        self._backend = backend
        self._lock = Lock()

    @property
    def inner(self):
        """The wrapped backend. Use only where you hold no lock expectation."""
        return self._backend

    def save(self, item: ContextItem, subtask_id: Optional[str] = None) -> bool:
        with self._lock:
            return self._backend.save(item, subtask_id=subtask_id)

    def get(self, item_id: str, tenant_id: Optional[str] = None) -> Optional[ContextItem]:
        with self._lock:
            return self._backend.get(item_id, tenant_id=tenant_id)

    def query(
        self,
        tier: Tier,
        scope: Optional[Scope] = None,
        subtask_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        include_global: bool = False,
        limit: Optional[int] = None,
    ) -> List[ContextItem]:
        with self._lock:
            return self._backend.query(
                tier,
                scope=scope,
                subtask_id=subtask_id,
                tenant_id=tenant_id,
                include_global=include_global,
                limit=limit,
            )

    def stored(self, item_id: str, tenant_id: Optional[str] = None) -> Optional[StoredItem]:
        with self._lock:
            return self._backend.stored(item_id, tenant_id=tenant_id)

    def search(
        self,
        tenant_id: Optional[str] = None,
        global_tiers: Sequence[Tier] = (),
        tiers: Optional[Sequence[Tier]] = None,
        scope: Optional[Scope] = None,
        text: str = "",
        owner_id: str = "",
        session_id: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[List[StoredItem], int]:
        with self._lock:
            return self._backend.search(
                tenant_id=tenant_id,
                global_tiers=global_tiers,
                tiers=tiers,
                scope=scope,
                text=text,
                owner_id=owner_id,
                session_id=session_id,
                limit=limit,
                offset=offset,
            )

    def list_subtasks(self, tenant_id: Optional[str] = None) -> List[Tuple[str, int]]:
        with self._lock:
            return self._backend.list_subtasks(tenant_id=tenant_id)

    def count(
        self,
        tier: Tier,
        tenant_id: Optional[str] = None,
        include_global: bool = False,
    ) -> int:
        with self._lock:
            return self._backend.count(tier, tenant_id=tenant_id, include_global=include_global)

    def delete(self, item_id: str, tenant_id: Optional[str] = None) -> bool:
        with self._lock:
            return self._backend.delete(item_id, tenant_id=tenant_id)

    def delete_by_scope(
        self,
        scope: Scope,
        tier: Optional[Tier] = None,
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> int:
        with self._lock:
            return self._backend.delete_by_scope(
                scope,
                tier=tier,
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
            )

    def delete_tenant(self, tenant_id: str) -> int:
        with self._lock:
            return self._backend.delete_tenant(tenant_id)

    def purge_expired(
        self,
        now: Optional[float] = None,
        tenant_id: Optional[str] = None,
    ) -> int:
        with self._lock:
            return self._backend.purge_expired(now=now, tenant_id=tenant_id)

    def list_tenants(self) -> List[str]:
        with self._lock:
            return self._backend.list_tenants()
