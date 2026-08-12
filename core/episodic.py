from typing import List, Optional

from core.identity import Principal
from core.proto.trilith_pb2 import Scope, Tier
from core.store_base import BaseStore, parse_scope


class EpisodicStore(BaseStore):
    """Scoped events. Never cross a tenant boundary, and physically forgettable."""

    tier = Tier.EPISODIC
    # Episodic events stay inside their tenant even when marked GLOBAL.
    include_global = False

    def query(
        self,
        filter: str = "",
        budget_tokens: int = 0,
        scope: str = "",
        principal: Optional[Principal] = None,
        limit: Optional[int] = None,
    ):
        """Query episodic events.

        With a principal, reads are confined to that principal's tenant, which
        is the isolation the old scope-string rule was approximating.

        Without one, the v0.1 guard still applies: a bare scope string is the
        only thing standing between the caller and every tenant's events, so a
        missing or too-broad scope is rejected rather than silently widened.
        """
        if principal is not None:
            return self.query_for(principal, limit=limit)

        if not scope:
            raise ValueError(
                "Episodic query must specify a valid scope to prevent cross-tenant exposure."
            )

        scope_enum = parse_scope(scope)
        if scope_enum is None:
            # Unrecognised scope name: nothing can match it.
            return []

        if scope_enum in (Scope.SCOPE_UNSPECIFIED, Scope.GLOBAL):
            raise KeyError(
                "Episodic query cannot use UNSPECIFIED or GLOBAL scope to avoid cross-tenant reads."
            )

        return self.backend.query(Tier.EPISODIC, scope=scope_enum, limit=limit)

    def forget(
        self,
        scope: str,
        notify_stores: Optional[List] = None,
        principal: Optional[Principal] = None,
    ) -> int:
        """Physically delete every item of `scope`, cascading across tiers.

        With a principal the purge is confined to that tenant — and further to
        the caller's own `owner_id`/`session_id` when the scope is USER or
        SESSION, so "forget me" cannot become "forget everyone".

        Returns:
            Number of episodic items deleted.
        """
        notify_stores = notify_stores or []

        scope_enum = parse_scope(scope)
        if scope_enum is None:
            return 0

        tenant_id = principal.tenant_id if principal else None
        owner_id = ""
        session_id = ""
        if principal is not None:
            if scope_enum == Scope.USER:
                owner_id = principal.owner_id
            elif scope_enum == Scope.SESSION:
                session_id = principal.session_id

        # Cascade to the other tiers first, then purge our own.
        for store in notify_stores:
            backend = getattr(store, "backend", None)
            if backend is None or not hasattr(backend, "delete_by_scope"):
                continue
            backend.delete_by_scope(
                scope_enum,
                tier=getattr(store, "tier", None),
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=session_id,
            )

        return self.backend.delete_by_scope(
            scope_enum,
            tier=self.tier,
            tenant_id=tenant_id,
            owner_id=owner_id,
            session_id=session_id,
        )

    def forget_tenant(self, tenant_id: str) -> int:
        """Erase an entire tenant across all tiers. Used for offboarding."""
        return self.backend.delete_tenant(tenant_id)
