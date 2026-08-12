"""Shared behaviour for the three tier stores.

Each tier exposes two read paths:

* ``query(...)`` — the v0.1 signature, kept working for existing callers.
  Without a principal it does not restrict by tenant.
* ``query_for(principal, ...)`` — the tenant-scoped path the Governor uses.
  It never returns another tenant's items, and it never raises: an
  unaddressable tier yields an empty list rather than failing the assembly.
"""

from __future__ import annotations

from typing import List, Optional

from core.identity import Principal
from core.proto.trilith_pb2 import ContextItem, Scope, Tier


def parse_scope(scope: str) -> Optional[int]:
    """'user' -> Scope.USER. Returns None for empty or unrecognised names."""
    if not scope:
        return None
    try:
        return Scope.Value(scope.upper())
    except ValueError:
        return None


class BaseStore:
    tier: Tier = Tier.TIER_UNSPECIFIED
    # GLOBAL items are cross-tenant, so semantic/procedural reads include them.
    # Episodic overrides this to False: events never leave their tenant.
    include_global = True

    def __init__(self, backend=None):
        if backend is None:
            from core.sqlite_backend import SQLiteBackend

            backend = SQLiteBackend()
        self.backend = backend

    def write(self, item: ContextItem, **kwargs) -> bool:
        item.tier = self.tier
        return self.backend.save(item, **kwargs)

    def query(
        self,
        filter: str = "",
        budget_tokens: int = 0,
        scope: str = "",
        principal: Optional[Principal] = None,
        limit: Optional[int] = None,
    ) -> List[ContextItem]:
        if principal is not None:
            return self.query_for(principal, limit=limit)

        # Legacy path: filter by scope name only, across all tenants.
        return self.backend.query(self.tier, scope=parse_scope(scope), limit=limit)

    def query_for(
        self,
        principal: Principal,
        limit: Optional[int] = None,
    ) -> List[ContextItem]:
        """Candidates visible to `principal`'s tenant, newest first."""
        return self.backend.query(
            self.tier,
            tenant_id=principal.tenant_id,
            include_global=self.include_global,
            limit=limit,
        )

    def count_for(self, principal: Principal) -> int:
        return self.backend.count(
            self.tier,
            tenant_id=principal.tenant_id,
            include_global=self.include_global,
        )
