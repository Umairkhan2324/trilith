"""FastAPI REST gateway for Trilith."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Header, HTTPException
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel

from core.auth import AuthError
from core.identity import Principal
from core.ops import fold_subtask, forget_scope, purge_expired, write_item
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import TrilithRuntime


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


class AssembleBody(_TenantAware):
    task: str
    budget: Optional[int] = 200
    # Legacy v0.1 field. Prefer tenant_id/owner_id/session_id.
    requester_scope: Optional[str] = None


class ForgetBody(_TenantAware):
    scope: str


class FoldBody(_TenantAware):
    subtask_id: str


class PurgeBody(_TenantAware):
    pass


def create_rest_app(rt: TrilithRuntime) -> FastAPI:
    app = FastAPI(
        title="Trilith Context Management API",
        description="Language-agnostic context management layer for AI systems.",
        version="0.2.0",
    )

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

    @app.get("/healthz")
    def health():
        return {
            "status": "ok",
            "service": "trilith-core",
            "version": "0.2.0",
            "auth_enabled": rt.auth.enabled,
        }

    @app.get("/v1/whoami")
    def whoami(authorization: Optional[str] = Header(default=None)):
        """Echo the identity Trilith resolved — the fastest way to debug auth."""
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

    @app.post("/v1/write")
    def write(body: WriteBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        try:
            tier_enum = Tier.Value(body.tier.upper())
            scope_enum = Scope.Value(body.scope.upper())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
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
        ack = write_item(rt, item, principal=principal)
        if not ack.success:
            raise HTTPException(status_code=400, detail=ack.message)
        return {"success": True, "id": body.id, "tenant_id": item.tenant_id}

    @app.post("/v1/assemble")
    def assemble(body: AssembleBody, authorization: Optional[str] = Header(default=None)):
        principal = principal_for(body, authorization)
        assembled = rt.governor.assemble(
            task=body.task,
            budget=body.budget,
            principal=principal,
        )
        return {
            "items": [
                {
                    "id": i.id,
                    "tier": Tier.Name(i.tier),
                    "scope": Scope.Name(i.scope),
                    "content": i.content,
                    "tenant_id": i.tenant_id,
                }
                for i in assembled.items
            ],
            "tokens_used": assembled.tokens_used,
            "excluded_items": [
                {"id": ex.item.id, "reason": ex.reason}
                for ex in assembled.excluded_items
            ],
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
