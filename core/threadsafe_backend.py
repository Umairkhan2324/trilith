"""Thread-safe wrapper around a store backend (REST + gRPC share one DB)."""

from __future__ import annotations

from threading import Lock
from typing import List, Optional

from core.proto.trilith_pb2 import ContextItem, Scope, Tier


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

    def count(
        self,
        tier: Tier,
        tenant_id: Optional[str] = None,
        include_global: bool = False,
    ) -> int:
        with self._lock:
            return self._backend.count(
                tier, tenant_id=tenant_id, include_global=include_global
            )

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
