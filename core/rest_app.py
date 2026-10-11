"""FastAPI REST gateway for Trilith.

Three groups of endpoints:

* **Pipeline** - `write` / `assemble` / `forget` / `fold` / `purge-expired`.
  What an agent calls.
* **Inspection** - `dashboard` / `items` / `subtasks` / `events` / `whoami`.
  What a console reads to show an operator the live state.
* **Editing** - `PATCH` and `DELETE` on a single item. What makes that console
  able to change context instead of only watching it.

Inspection and editing are tenant-scoped exactly like the pipeline: the same
`Principal` resolution, the same SQL boundary. Within a tenant they are
deliberately an *admin* view - stored content is returned unredacted, and items
the policy would refuse are listed with the refusal reason rather than hidden.
`assemble` is unchanged: it still redacts, and still returns only what the
policy allows.
"""

from __future__ import annotations

import math
import time
from typing import List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel

from core import __version__
from core.auth import AuthError
from core.governor import BUDGET_EXCEEDED, RELEVANCE_FLOOR
from core.identity import Principal
from core.ops import (
    assemble_context,
    delete_item,
    fold_subtask,
    forget_scope,
    purge_expired,
    update_item,
    write_item,
)
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import TrilithRuntime
from core.sqlite_backend import StoredItem

# The budget a caller gets when they do not choose one. Named once so the
# model default and the null-handling below cannot drift apart.
DEFAULT_BUDGET = 200


class _TenantAware(BaseModel):
    """Identity a client may supply. Ignored for fields the API key pins."""

    tenant_id: Optional[str] = None
    owner_id: Optional[str] = None
    session_id: Optional[str] = None


class WriteBody(_TenantAware):
    id: str
    tier: str
    content: str
    scope: str
    provenance: Optional[str] = ""
    # Groups procedural steps so `fold` can collapse them. Storage-level, not
    # part of ContextItem - see core.ops.write_item.
    subtask_id: Optional[str] = None
    # Relative TTL. The stored field is an absolute `expires_at`; a caller
    # should not have to compute it, and a console should not have to guess it.
    ttl_seconds: Optional[int] = None


class ItemPatch(_TenantAware):
    """Fields to change. Anything left `None` keeps its stored value."""

    content: Optional[str] = None
    tier: Optional[str] = None
    scope: Optional[str] = None
    provenance: Optional[str] = None
    subtask_id: Optional[str] = None
    # 0 clears the expiry; a positive value re-dates it from now.
    ttl_seconds: Optional[int] = None


class AssembleBody(_TenantAware):
    task: str
    # Optional means "omit it and get the default". An explicit null means the
    # same thing - it used to mean a 500 out of the governor's fill loop.
    budget: Optional[int] = DEFAULT_BUDGET
    # Legacy v0.1 field. Prefer tenant_id/owner_id/session_id.
    requester_scope: Optional[str] = None


class ForgetBody(_TenantAware):
    scope: str


class FoldBody(_TenantAware):
    subtask_id: str


class PurgeBody(_TenantAware):
    pass


def _parse_tier(name: str) -> int:
    try:
        return Tier.Value(name.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown tier '{name}'") from exc


def _parse_scope(name: str) -> int:
    try:
        return Scope.Value(name.upper())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown scope '{name}'") from exc


def _apply_ttl(item: ContextItem, ttl_seconds: Optional[int]) -> None:
    """Translate a relative TTL into the absolute expiry the store keeps.

    `None` leaves the expiry alone and exactly `0` removes it. Any other value
    is an offset from now, so a negative one expires the item immediately -
    which is how a console retires something without deleting it outright.
    """
    if ttl_seconds is None:
        return
    if ttl_seconds == 0:
        item.ClearField("expires_at")
        return
    expires = Timestamp()
    expires.FromSeconds(int(time.time()) + int(ttl_seconds))
    item.expires_at.CopyFrom(expires)


def create_rest_app(rt: TrilithRuntime) -> FastAPI:
    app = FastAPI(
        title="Trilith Context Management API",
        description="Language-agnostic context management layer for AI systems.",
        version=__version__,
    )

    from fastapi.responses import JSONResponse

    @app.exception_handler(PermissionError)
    async def permission_error(request, exc):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    tiers = (
        ("SEMANTIC", Tier.SEMANTIC, rt.semantic),
        ("PROCEDURAL", Tier.PROCEDURAL, rt.procedural),
        ("EPISODIC", Tier.EPISODIC, rt.episodic),
    )
    # Tiers whose GLOBAL items are readable across tenants. Episodic is not one
    # of them, and the browse path must honour the same rule the stores do.
    global_tiers = tuple(tier for _, tier, store in tiers if store.include_global)

    def principal_for(body: _TenantAware, authorization: Optional[str]) -> Principal:
        """Resolve the request's identity, or 401.

        With auth disabled the body is trusted (local/dev). With auth enabled
        the API key decides the tenant and the body cannot override it.
        """
        try:
            return rt.auth.resolve(
                authorization,
                tenant_id=body.tenant_id or "",
                owner_id=body.owner_id or "",
                session_id=body.session_id or "",
                legacy_scope=getattr(body, "requester_scope", None) or "",
            )
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def principal_from_query(
        authorization: Optional[str],
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Principal:
        """Same resolution for GET endpoints, where identity arrives as query."""
        try:
            return rt.auth.resolve(
                authorization,
                tenant_id=tenant_id or "",
                owner_id=owner_id or "",
                session_id=session_id or "",
            )
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def require_admin(principal: Principal) -> None:
        if not principal.can("tenant_admin"):
            raise HTTPException(status_code=403, detail="tenant_admin capability required")

    def item_payload(stored: StoredItem, principal: Principal) -> dict:
        """One row as a console needs it: content, cost, and admissibility."""
        item = stored.item
        if rt.governor.policy_engine is not None:
            visible, reason = rt.governor.policy_engine.explain(item, principal)
        else:
            visible, reason = True, ""
        return {
            "id": item.id,
            "tier": Tier.Name(item.tier),
            "scope": Scope.Name(item.scope),
            "content": item.content,
            "provenance": item.provenance,
            "created_at": item.created_at.ToJsonString(),
            "expires_at": (item.expires_at.ToJsonString() if item.HasField("expires_at") else None),
            "tenant_id": item.tenant_id,
            "owner_id": item.owner_id,
            "session_id": item.session_id,
            "subtask_id": stored.subtask_id or "",
            "tokens": rt.governor.estimate_tokens(item),
            "visible": visible,
            "visibility_reason": reason,
        }

    def identity_payload(principal: Principal) -> dict:
        return {
            "tenant_id": principal.tenant_id,
            "owner_id": principal.owner_id,
            "session_id": principal.session_id,
        }

    # --- Health and identity ------------------------------------------------

    @app.get("/healthz")
    def health():
        return {
            "status": "ok",
            "service": "trilith-core",
            "version": __version__,
            "auth_enabled": rt.auth.enabled,
        }

    @app.get("/v1/whoami")
    def whoami(authorization: Optional[str] = Header(default=None)):
        """Echo the identity Trilith resolved - the fastest way to debug auth."""
        try:
            p = rt.auth.resolve(authorization)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        return {
            "tenant_id": p.tenant_id,
            "owner_id": p.owner_id,
            "session_id": p.session_id,
            "auth_enabled": rt.auth.enabled,
        }

    # --- Inspection ---------------------------------------------------------

    @app.get("/v1/dashboard")
    def dashboard(
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
        limit: int = 12,
    ):
        """Tenant-scoped operational snapshot for human-facing consoles."""
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)

        safe_limit = max(1, min(limit, 50))
        counts = {}
        recent = []
        for name, tier, store in tiers:
            counts[name] = rt.backend.count(
                tier,
                tenant_id=principal.tenant_id,
                include_global=store.include_global,
            )
            items = rt.backend.query(
                tier,
                tenant_id=principal.tenant_id,
                include_global=store.include_global,
                limit=safe_limit,
            )
            recent.extend(
                {
                    "id": item.id,
                    "tier": name,
                    "scope": Scope.Name(item.scope),
                    "content": item.content,
                    "provenance": item.provenance,
                    "created_at": item.created_at.ToJsonString(),
                    "owner_id": item.owner_id,
                    "session_id": item.session_id,
                }
                for item in items
            )

        recent.sort(key=lambda item: item["created_at"], reverse=True)
        return {
            "service": "trilith-core",
            "version": __version__,
            "status": "operational",
            "auth_enabled": rt.auth.enabled,
            "identity": identity_payload(principal),
            "counts": counts,
            "total_items": sum(counts.values()),
            "recent_items": recent[:safe_limit],
            # Cursor a console hands back to /v1/events to stream on from here.
            "latest_event_seq": rt.events.latest_seq,
        }

    @app.get("/v1/items")
    def list_items(
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
        tier: Optional[str] = None,
        scope: Optional[str] = None,
        q: str = "",
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ):
        """Browse and search the tenant's stored context, newest first.

        Every row carries `tokens` (what it would cost an assembly) and
        `visible` / `visibility_reason` (whether the current identity could
        actually receive it). A row that is stored but unreachable is the thing
        an operator most needs to see, so it is listed, not omitted.
        """
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)

        selected_tiers = [_parse_tier(tier)] if tier else None
        selected_scope = _parse_scope(scope) if scope else None
        allowed_global = tuple(
            t for t in global_tiers if selected_tiers is None or t in selected_tiers
        )

        page, total = rt.backend.search(
            tenant_id=principal.tenant_id,
            global_tiers=allowed_global,
            tiers=selected_tiers,
            scope=selected_scope,
            text=q,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [item_payload(stored, principal) for stored in page],
            "total": total,
            "limit": limit,
            "offset": offset,
            "identity": identity_payload(principal),
        }

    @app.get("/v1/items/{item_id}")
    def get_item(
        item_id: str,
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)
        require_admin(principal)
        stored = rt.backend.stored(item_id, tenant_id=principal.tenant_id)
        if stored is None:
            raise HTTPException(status_code=404, detail=f"No item '{item_id}' in this tenant")
        return item_payload(stored, principal)

    @app.get("/v1/subtasks")
    def list_subtasks(
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        """Procedural sub-tasks that currently hold steps - the fold candidates."""
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)
        groups = rt.backend.list_subtasks(tenant_id=principal.tenant_id)
        return {"subtasks": [{"subtask_id": name, "steps": steps} for name, steps in groups]}

    @app.get("/v1/events")
    def list_events(
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
        after: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=500),
    ):
        """Recent operations for this tenant, oldest first, after a cursor.

        In-memory and bounded (see core.events): this reports live traffic, it
        is not a durable audit log.
        """
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)
        events = rt.events.since(after=after, tenant_id=principal.tenant_id, limit=limit)
        return {
            "events": [event.to_dict() for event in events],
            "latest_seq": rt.events.latest_seq,
        }

    @app.get("/v1/tenants")
    def list_tenants(authorization: Optional[str] = Header(default=None)):
        """Tenants holding data.

        With auth on, a key is bound to one tenant and that is all it may know
        about, so the list is just its own - the names of neighbouring tenants
        are themselves a leak.
        """
        try:
            principal = rt.auth.resolve(authorization)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        if rt.auth.enabled:
            return {"tenants": [principal.tenant_id], "scoped": True}
        return {"tenants": rt.backend.list_tenants(), "scoped": False}

    # --- Pipeline -----------------------------------------------------------

    @app.post("/v1/write")
    def write(body: WriteBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        tier_enum = _parse_tier(body.tier)
        scope_enum = _parse_scope(body.scope)
        ts = Timestamp()
        ts.GetCurrentTime()
        item = ContextItem(
            id=body.id,
            tier=tier_enum,
            scope=scope_enum,
            content=body.content,
            provenance=body.provenance or "",
            created_at=ts,
            owner_id=body.owner_id or "",
            session_id=body.session_id or "",
        )
        _apply_ttl(item, body.ttl_seconds)
        ack = write_item(rt, item, principal=principal, subtask_id=body.subtask_id or None)
        if not ack.success:
            raise HTTPException(status_code=400, detail=ack.message)
        return {"success": True, "id": body.id, "tenant_id": item.tenant_id}

    @app.patch("/v1/items/{item_id}")
    def patch_item(
        item_id: str,
        body: ItemPatch,
        authorization: Optional[str] = Header(default=None),
    ):
        """Edit a stored item in place.

        Read-merge-write against the row as it exists in the caller's tenant,
        so an edit can never reach across the boundary and never silently drops
        the columns it was not asked to change.
        """
        principal = principal_for(body, authorization)
        require_admin(principal)
        stored = rt.backend.stored(item_id, tenant_id=principal.tenant_id)
        if stored is None:
            raise HTTPException(status_code=404, detail=f"No item '{item_id}' in this tenant")

        item = stored.item
        subtask_id = stored.subtask_id
        changed: List[str] = []

        if body.content is not None and body.content != item.content:
            item.content = body.content
            changed.append("content")
        if body.tier is not None:
            tier_enum = _parse_tier(body.tier)
            if tier_enum != item.tier:
                item.tier = tier_enum
                changed.append("tier")
        if body.scope is not None:
            scope_enum = _parse_scope(body.scope)
            if scope_enum != item.scope:
                item.scope = scope_enum
                changed.append("scope")
        if body.provenance is not None and body.provenance != item.provenance:
            item.provenance = body.provenance
            changed.append("provenance")
        if body.owner_id is not None and body.owner_id != item.owner_id:
            item.owner_id = body.owner_id
            changed.append("owner_id")
        if body.session_id is not None and body.session_id != item.session_id:
            item.session_id = body.session_id
            changed.append("session_id")
        if body.subtask_id is not None and (body.subtask_id or None) != subtask_id:
            subtask_id = body.subtask_id or None
            changed.append("subtask_id")
        if body.ttl_seconds is not None:
            _apply_ttl(item, body.ttl_seconds)
            changed.append("expires_at")

        if not changed:
            return {"success": True, "id": item_id, "changed": [], "item": None}

        ack = update_item(rt, item, principal=principal, subtask_id=subtask_id, changed=changed)
        if not ack.success:
            raise HTTPException(status_code=400, detail=ack.message)
        refreshed = rt.backend.stored(item_id, tenant_id=principal.tenant_id)
        return {
            "success": True,
            "id": item_id,
            "changed": changed,
            "item": item_payload(refreshed, principal) if refreshed else None,
        }

    @app.delete("/v1/items/{item_id}")
    def remove_item(
        item_id: str,
        authorization: Optional[str] = Header(default=None),
        tenant_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ):
        principal = principal_from_query(authorization, tenant_id, owner_id, session_id)
        require_admin(principal)
        if not delete_item(rt, item_id, principal=principal):
            raise HTTPException(status_code=404, detail=f"No item '{item_id}' in this tenant")
        return {"success": True, "id": item_id, "tenant_id": principal.tenant_id}

    @app.post("/v1/assemble")
    def assemble(body: AssembleBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        budget = DEFAULT_BUDGET if body.budget is None else body.budget
        assembled = assemble_context(
            rt,
            task=body.task,
            budget=budget,
            principal=principal,
        )

        def excluded_payload(excluded) -> dict:
            item = excluded.item
            if excluded.reason == BUDGET_EXCEEDED:
                kind = "budget"
            elif excluded.reason.startswith(RELEVANCE_FLOOR):
                kind = "relevance"
            else:
                kind = "policy"
            return {
                "id": item.id,
                "tier": Tier.Name(item.tier),
                "scope": Scope.Name(item.scope),
                "reason": excluded.reason,
                "kind": kind,
                # Budget and relevance drops already cleared the policy, so
                # their (redacted) content is safe to echo - and it is what an
                # operator needs to judge whether the ranker was right. Policy
                # denials are not: handing over the content of something the
                # caller may not read would undo the decision being reported.
                "content": "" if kind == "policy" else item.content,
                "tokens": rt.governor.estimate_tokens(item),
            }

        return {
            "items": [
                {
                    "id": i.id,
                    "tier": Tier.Name(i.tier),
                    "scope": Scope.Name(i.scope),
                    "content": i.content,
                    "tenant_id": i.tenant_id,
                    "tokens": rt.governor.estimate_tokens(i),
                }
                for i in assembled.items
            ],
            "tokens_used": assembled.tokens_used,
            "budget": budget,
            "task": body.task,
            # JSON has no infinity, and a disabled floor is exactly that. Null
            # reads as "no relevance floor", which is what it means.
            "min_score": (rt.governor.min_score if math.isfinite(rt.governor.min_score) else None),
            "excluded_items": [excluded_payload(ex) for ex in assembled.excluded_items],
            "candidates_truncated": assembled.candidates_truncated,
            "tenant_id": principal.tenant_id,
        }

    @app.post("/v1/forget")
    def forget(body: ForgetBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        count = forget_scope(rt, body.scope, principal=principal)
        return {
            "success": True,
            "deleted_episodic_count": count,
            "tenant_id": principal.tenant_id,
        }

    @app.post("/v1/fold")
    def fold(body: FoldBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        summary, folded_count = fold_subtask(rt, body.subtask_id, principal=principal)
        if summary is None:
            return {
                "success": False,
                "message": f"No procedural steps found for subtask '{body.subtask_id}'",
                "folded_count": 0,
                "item": None,
            }
        return {
            "success": True,
            "message": f"Folded {folded_count} steps",
            "folded_count": folded_count,
            "item": {"id": summary.id, "content": summary.content},
        }

    @app.post("/v1/purge-expired")
    def purge(body: PurgeBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        deleted = purge_expired(rt, principal=principal)
        return {"success": True, "deleted_count": deleted}

    return app
