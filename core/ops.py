"""Shared write/query/forget/fold operations used by REST and gRPC gateways."""

from __future__ import annotations

from typing import List, Optional, Tuple

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.proto.trilith_pb2 import ContextItem, QueryResponse, Tier, WriteAck
from core.runtime import TrilithRuntime


def ensure_created_at(item: ContextItem) -> None:
    if not item.HasField("created_at"):
        ts = Timestamp()
        ts.GetCurrentTime()
        item.created_at.CopyFrom(ts)


def write_item(
    rt: TrilithRuntime,
    item: ContextItem,
    principal: Optional[Principal] = None,
) -> WriteAck:
    ensure_created_at(item)

    # The principal owns the write: its tenant is stamped onto the item, so a
    # caller cannot plant data inside someone else's tenant.
    if principal is not None:
        principal.stamp(item)

    if item.tier == Tier.SEMANTIC:
        rt.semantic.write(item)
    elif item.tier == Tier.PROCEDURAL:
        rt.procedural.write(item)
    elif item.tier == Tier.EPISODIC:
        rt.episodic.write(item)
    else:
        return WriteAck(success=False, message="Invalid or unspecified tier")
    return WriteAck(success=True, message=f"Wrote {item.id}")


def query_items(
    rt: TrilithRuntime,
    tier: Tier,
    filter_text: str = "",
    budget_tokens: int = 0,
    scope: str = "",
    principal: Optional[Principal] = None,
) -> QueryResponse:
    store = {
        Tier.SEMANTIC: rt.semantic,
        Tier.PROCEDURAL: rt.procedural,
        Tier.EPISODIC: rt.episodic,
    }.get(tier)
    if store is None:
        return QueryResponse(items=[])
    items: List[ContextItem] = store.query(
        filter=filter_text,
        budget_tokens=budget_tokens,
        scope=scope,
        principal=principal,
    )
    return QueryResponse(items=items)


def forget_scope(
    rt: TrilithRuntime,
    scope: str,
    principal: Optional[Principal] = None,
) -> int:
    return rt.episodic.forget(
        scope=scope,
        notify_stores=[rt.semantic, rt.procedural],
        principal=principal,
    )


def fold_subtask(
    rt: TrilithRuntime,
    subtask_id: str,
    principal: Optional[Principal] = None,
) -> Tuple[Optional[ContextItem], int]:
    """Collapse a procedural sub-task into one summary item.

    Returns (summary_item, folded_step_count). The item is None when the
    sub-task has no steps visible to this principal.
    """
    tenant = principal.tenant_id if principal else None
    before = rt.backend.query(Tier.PROCEDURAL, subtask_id=subtask_id, tenant_id=tenant)
    if not before:
        return None, 0
    summary = rt.procedural.fold(subtask_id, principal=principal)
    return summary, len(before)


def purge_expired(rt: TrilithRuntime, principal: Optional[Principal] = None) -> int:
    """Physically delete items past their TTL for this tenant (or all tenants)."""
    tenant = principal.tenant_id if principal else None
    return rt.backend.purge_expired(tenant_id=tenant)
