from typing import List, Optional
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.sqlite_backend import SQLiteBackend

class EpisodicStore:
    def __init__(self, backend=None):
        self.backend = backend or SQLiteBackend()
        self.tier = Tier.EPISODIC

    def write(self, item: ContextItem) -> bool:
        # Guarantee item's tier is EPISODIC
        item.tier = Tier.EPISODIC
        return self.backend.save(item)

    def query(self, filter: str = "", budget_tokens: int = 0, scope: str = "") -> List[ContextItem]:
        """Query episodic store.

        A scope MUST be provided to query episodic store. No accidental cross-tenant reads.
        """
        if not scope:
            raise ValueError("Episodic query must specify a valid scope to prevent cross-tenant exposure.")
            
        try:
            scope_enum = Scope.Value(scope.upper())
        except ValueError:
            # If the scope is invalid, return empty list
            return []
            
        # Scope cannot be UNSPECIFIED or GLOBAL for episodic memory queries to ensure isolated tenants
        if scope_enum in (Scope.SCOPE_UNSPECIFIED, Scope.GLOBAL):
            raise KeyError("Episodic query cannot use UNSPECIFIED or GLOBAL scope to avoid cross-tenant reads.")

        return self.backend.query(Tier.EPISODIC, scope=scope_enum)

    def forget(self, scope: str, notify_stores: List = []) -> int:
        """Deletes all items with matching scope from EpisodicStore.

        Also notifies Semantic/Procedural stores to purge anything with the matching scope.
        Returns:
            Number of items deleted from this EpisodicStore database.
        """
        try:
            scope_enum = Scope.Value(scope.upper())
        except ValueError:
            return 0

        # Delete from other stores if they are passed in
        for store in notify_stores:
            if hasattr(store, "backend") and hasattr(store.backend, "delete_by_scope"):
                tier_val = getattr(store, "tier", None)
                store.backend.delete_by_scope(scope_enum, tier=tier_val)

        # Delete from local backend
        count = self.backend.delete_by_scope(scope_enum, tier=self.tier)
        return count
