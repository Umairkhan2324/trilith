from typing import List, Optional
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.sqlite_backend import SQLiteBackend

class SemanticStore:
    def __init__(self, backend=None):
        self.backend = backend or SQLiteBackend()
        self.tier = Tier.SEMANTIC

    def write(self, item: ContextItem) -> bool:
        # Guarantee item's tier isSEMANTIC
        item.tier = Tier.SEMANTIC
        return self.backend.save(item)

    def query(self, filter: str = "", budget_tokens: int = 0, scope: str = "") -> List[ContextItem]:
        scope_enum = None
        if scope:
            try:
                scope_enum = Scope.Value(scope.upper())
            except ValueError:
                pass
        
        # Simple SQLite DB query, then return all candidates.
        # Pluggable interface allows swapping this query out for an index search.
        return self.backend.query(Tier.SEMANTIC, scope=scope_enum)
