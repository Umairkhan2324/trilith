from typing import List, Optional
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.sqlite_backend import SQLiteBackend
from google.protobuf.timestamp_pb2 import Timestamp

class ProceduralStore:
    def __init__(self, backend=None):
        self.backend = backend or SQLiteBackend()
        self.tier = Tier.PROCEDURAL

    def write(self, item: ContextItem, subtask_id: Optional[str] = None) -> bool:
        # Guarantee item's tier is PROCEDURAL
        item.tier = Tier.PROCEDURAL
        return self.backend.save(item, subtask_id=subtask_id)

    def query(self, filter: str = "", budget_tokens: int = 0, scope: str = "") -> List[ContextItem]:
        scope_enum = None
        if scope:
            try:
                scope_enum = Scope.Value(scope.upper())
            except ValueError:
                pass
        
        return self.backend.query(Tier.PROCEDURAL, scope=scope_enum)

    def fold(self, subtask_id: str) -> Optional[ContextItem]:
        """Collapses a sequence of items matching subtask_id into one summary item.

        Deletes the original items from store and inserts the summary item.
        """
        # Query items for this subtask
        items = self.backend.query(Tier.PROCEDURAL, subtask_id=subtask_id)
        if not items:
            return None

        # Create collapsed description
        summary_content = f"Folded Procedural Context for subtask {subtask_id} containing {len(items)} steps:\n"
        # Preserve chronological order based on created_at if possible
        items_sorted = sorted(items, key=lambda x: (x.created_at.seconds, x.created_at.nanos))
        summary_content += "\n".join(f"- [{i.id}] {i.content}" for i in items_sorted)

        # Build collapsed context item
        summary_id = f"folded-{subtask_id}"
        
        # Find scope from items or default to GLOBAL
        first_scope = items_sorted[0].scope if items_sorted else Scope.GLOBAL
        
        created = Timestamp()
        created.GetCurrentTime()
        
        summary_item = ContextItem(
            id=summary_id,
            tier=Tier.PROCEDURAL,
            content=summary_content,
            scope=first_scope,
            provenance="procedural_fold",
            created_at=created
        )

        # Delete all original items
        for item in items:
            self.backend.delete(item.id)

        # Write summary item back under the same subtask_id (so it represents it)
        self.backend.save(summary_item, subtask_id=subtask_id)
        return summary_item
