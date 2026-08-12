from typing import List, Optional

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal, normalize_tenant
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.store_base import BaseStore


class ProceduralStore(BaseStore):
    """Task steps, foldable into a single summary once a sub-task is done."""

    tier = Tier.PROCEDURAL
    include_global = True

    def write(self, item: ContextItem, subtask_id: Optional[str] = None) -> bool:
        item.tier = Tier.PROCEDURAL
        return self.backend.save(item, subtask_id=subtask_id)

    def fold(
        self,
        subtask_id: str,
        principal: Optional[Principal] = None,
    ) -> Optional[ContextItem]:
        """Collapse the steps of one sub-task into a single summary item.

        The originals are deleted and replaced by the summary, which keeps a
        long-running task from growing its procedural footprint without bound.

        When a principal is given, only that tenant's steps are folded — one
        tenant can never collapse or read another's sub-task.
        """
        tenant = principal.tenant_id if principal else None

        items: List[ContextItem] = self.backend.query(
            Tier.PROCEDURAL,
            subtask_id=subtask_id,
            tenant_id=tenant,
        )
        if not items:
            return None

        # Preserve chronological order based on created_at if possible
        items_sorted = sorted(items, key=lambda x: (x.created_at.seconds, x.created_at.nanos))

        summary_content = (
            f"Folded Procedural Context for subtask {subtask_id} "
            f"containing {len(items)} steps:\n"
        )
        summary_content += "\n".join(f"- [{i.id}] {i.content}" for i in items_sorted)

        first = items_sorted[0]
        created = Timestamp()
        created.GetCurrentTime()

        summary_item = ContextItem(
            id=f"folded-{subtask_id}",
            tier=Tier.PROCEDURAL,
            content=summary_content,
            scope=first.scope if items_sorted else Scope.GLOBAL,
            provenance="procedural_fold",
            created_at=created,
            tenant_id=normalize_tenant(principal.tenant_id if principal else first.tenant_id),
            owner_id=first.owner_id,
            session_id=first.session_id,
        )

        for item in items:
            self.backend.delete(item.id, tenant_id=tenant)

        # Write the summary back under the same subtask_id, so it stands in
        # for the steps it replaced.
        self.backend.save(summary_item, subtask_id=subtask_id)
        return summary_item
