"""Shared write/query/forget/fold operations used by REST and gRPC gateways.

Every mutation and every assembly is recorded on `rt.events`, so a console
sees the whole instance's traffic — an agent writing over gRPC shows up next
to an operator editing a row in the browser.
"""

from __future__ import annotations

from functools import wraps
from typing import List, Optional, Tuple

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.privacy import PolicyEngine
from core.proto.trilith_pb2 import (
    AssembledContext,
    ContextItem,
    QueryResponse,
    Scope,
    Tier,
    WriteAck,
)
from core.runtime import TrilithRuntime


def atomic_operation(function):
    @wraps(function)
    def wrapped(rt, *args, **kwargs):
        with rt.backend.transaction():
            return function(rt, *args, **kwargs)

    return wrapped


def ensure_created_at(item: ContextItem) -> None:
    if not item.HasField("created_at"):
        ts = Timestamp()
        ts.GetCurrentTime()
        item.created_at.CopyFrom(ts)


def _preview(text: str, width: int = 90) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else f"{text[: width - 1]}…"


def store_for(rt: TrilithRuntime, tier: Tier):
    return {
        Tier.SEMANTIC: rt.semantic,
        Tier.PROCEDURAL: rt.procedural,
        Tier.EPISODIC: rt.episodic,
    }.get(tier)


def write_denial(rt, item, principal):
    if principal is None:
        return ""  # Embedded callers are trusted; network gateways always bind a principal.
    existing = rt.backend.get(item.id, tenant_id=principal.tenant_id)
    if (
        item.scope == Scope.GLOBAL or (existing and existing.scope == Scope.GLOBAL)
    ) and not principal.can("publish_global"):
        return "publish_global capability required"
    if not principal.can("tenant_admin"):
        for candidate in (existing, item):
            if (
                candidate is not None
                and not PolicyEngine()._check_visibility(candidate, principal)[0]
            ):
                return "Item is outside principal scope"
        if item.scope == Scope.USER and not item.owner_id:
            return "USER requires owner_id"
        if item.scope == Scope.SESSION and not item.session_id:
            return "SESSION requires session_id"
    return ""


@atomic_operation
def write_item(
    rt: TrilithRuntime,
    item: ContextItem,
    principal: Optional[Principal] = None,
    subtask_id: Optional[str] = None,
) -> WriteAck:
    """Store an item in its tier.

    `subtask_id` groups procedural steps so `fold_subtask` can collapse them
    later. It is a storage column rather than a `ContextItem` field, which is
    why it travels beside the item instead of on it.
    """
    ensure_created_at(item)

    # The principal owns the write: its tenant is stamped onto the item, so a
    # caller cannot plant data inside someone else's tenant.
    if principal is not None:
        principal.stamp(item)

    denial = write_denial(rt, item, principal)
    if denial:
        rt.audit.record(principal, "write", "denied", reason=denial)
        return WriteAck(success=False, message=denial)

    store = store_for(rt, item.tier)
    if store is None:
        return WriteAck(success=False, message="Invalid or unspecified tier")
    store.write(item, subtask_id=subtask_id)
    rt.audit.record(principal, "write", "allowed", item_id=item.id)

    rt.events.record(
        "write",
        principal,
        f"wrote {Tier.Name(item.tier)}/{item.id}",
        id=item.id,
        tier=Tier.Name(item.tier),
        scope=Scope.Name(item.scope),
        subtask_id=subtask_id or "",
        preview=_preview(item.content),
    )
    return WriteAck(success=True, message=f"Wrote {item.id}")


@atomic_operation
def update_item(
    rt: TrilithRuntime,
    item: ContextItem,
    principal: Optional[Principal] = None,
    subtask_id: Optional[str] = None,
    changed: Optional[List[str]] = None,
) -> WriteAck:
    """Overwrite an existing row. The caller has already read and merged it.

    Separate from `write_item` only so the activity log can tell an edit from
    a fresh write; storage is the same upsert.

    Unlike `write_item` this does not stamp blank identity fields from the
    principal: an editor that clears `owner_id` means to clear it. The tenant
    is still forced, because that boundary is never the caller's to move.
    """
    if principal is not None:
        item.tenant_id = principal.tenant_id

    denial = write_denial(rt, item, principal)
    if denial:
        rt.audit.record(principal, "write", "denied", reason=denial)
        return WriteAck(success=False, message=denial)

    store = store_for(rt, item.tier)
    if store is None:
        return WriteAck(success=False, message="Invalid or unspecified tier")
    store.write(item, subtask_id=subtask_id)
    rt.audit.record(principal, "write", "allowed", item_id=item.id)

    rt.events.record(
        "update",
        principal,
        f"edited {Tier.Name(item.tier)}/{item.id}",
        id=item.id,
        tier=Tier.Name(item.tier),
        scope=Scope.Name(item.scope),
        fields=changed or [],
        preview=_preview(item.content),
    )
    return WriteAck(success=True, message=f"Updated {item.id}")


@atomic_operation
def delete_item(
    rt: TrilithRuntime,
    item_id: str,
    principal: Optional[Principal] = None,
) -> bool:
    """Physically remove one item, confined to the principal's tenant."""
    tenant = principal.tenant_id if principal else None
    existing = rt.backend.get(item_id, tenant_id=tenant)
    if existing and write_denial(rt, existing, principal):
        return False
    deleted = rt.backend.delete(item_id, tenant_id=tenant)
    if deleted:
        rt.events.record("delete", principal, f"deleted {item_id}", id=item_id)
    return deleted


def query_items(
    rt: TrilithRuntime,
    tier: Tier,
    filter_text: str = "",
    budget_tokens: int = 0,
    scope: str = "",
    principal: Optional[Principal] = None,
) -> QueryResponse:
    store = store_for(rt, tier)
    if store is None:
        return QueryResponse(items=[])
    items: List[ContextItem] = store.query(
        filter=filter_text,
        budget_tokens=budget_tokens,
        scope=scope,
        principal=principal,
    )
    if principal is not None:
        items, _ = PolicyEngine().filter(items, principal)
    if filter_text:
        ranked = rt.governor.rank(items, filter_text, budget_tokens)
        items = [item for item, score in ranked if score > rt.governor.min_score]
    if budget_tokens > 0:
        selected, spent = [], 0
        for item in items:
            cost = rt.governor.estimate_tokens(item)
            if spent + cost <= budget_tokens:
                selected.append(item)
                spent += cost
        items = selected
    return QueryResponse(items=items)


def assemble_context(
    rt: TrilithRuntime,
    task: str,
    budget: int,
    principal: Optional[Principal] = None,
) -> AssembledContext:
    """Run the governor and log the outcome.

    Assembly mutates nothing, but it is the operation people most need to
    watch — it is where the budget is spent and where items are dropped.
    """
    assembled = rt.governor.assemble(task=task, budget=budget, principal=principal)
    for item in assembled.items:
        rt.audit.record(principal, "assemble", "included", item_id=item.id, budget=budget)
    for excluded in assembled.excluded_items:
        rt.audit.record(
            principal, "assemble", "excluded", item_id=excluded.item.id, reason=excluded.reason
        )
    rt.events.record(
        "assemble",
        principal,
        f"assembled {len(assembled.items)} items for “{_preview(task, 60)}”",
        task=task,
        budget=budget,
        included=len(assembled.items),
        excluded=len(assembled.excluded_items),
        tokens_used=assembled.tokens_used,
        candidates_truncated=assembled.candidates_truncated,
    )
    return assembled


@atomic_operation
def forget_scope(
    rt: TrilithRuntime,
    scope: str,
    principal: Optional[Principal] = None,
) -> int:
    if principal and not principal.can("tenant_admin"):
        identity = principal.owner_id if scope.upper() == "USER" else principal.session_id
        if scope.upper() not in ("USER", "SESSION") or not identity:
            raise PermissionError("Scoped identity or tenant_admin capability required")
    if scope.upper() == "GLOBAL" and principal and not principal.can("publish_global"):
        raise PermissionError("publish_global capability required")
    count = rt.episodic.forget(
        scope=scope,
        notify_stores=[rt.semantic, rt.procedural],
        principal=principal,
    )
    if principal:
        rt.audit.erase(principal, scope)
    rt.events.clear()
    rt.audit.record(
        Principal(principal.tenant_id) if principal else None, "forget", "completed", count=count
    )
    rt.events.record(
        "forget",
        principal,
        f"forgot scope {scope.upper()} ({count} episodic items)",
        scope=scope.upper(),
        deleted_episodic_count=count,
    )
    return count


@atomic_operation
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
    if principal:
        before = [
            i
            for i in before
            if i.owner_id == principal.owner_id
            and i.session_id == principal.session_id
            and PolicyEngine().explain(i, principal)[0]
        ]
    if not before:
        return None, 0
    summary = rt.procedural.fold(subtask_id, principal=principal)
    rt.events.record(
        "fold",
        principal,
        f"folded {len(before)} steps of '{subtask_id}'",
        subtask_id=subtask_id,
        folded_count=len(before),
        id=summary.id if summary else "",
    )
    return summary, len(before)


def purge_expired(rt: TrilithRuntime, principal: Optional[Principal] = None) -> int:
    """Physically delete items past their TTL for this tenant (or all tenants)."""
    tenant = principal.tenant_id if principal else None
    deleted = rt.backend.purge_expired(tenant_id=tenant)
    rt.events.record(
        "purge",
        principal,
        f"purged {deleted} expired items",
        deleted_count=deleted,
    )
    return deleted
