"""FastAPI REST gateway for Trilith."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import BaseModel

from core.ops import forget_scope, write_item
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import TrilithRuntime


class WriteBody(BaseModel):
    id: str
    tier: str
    content: str
    scope: str
    provenance: Optional[str] = ""


class AssembleBody(BaseModel):
    task: str
    budget: Optional[int] = 200
    requester_scope: Optional[str] = "GLOBAL"


class ForgetBody(BaseModel):
    scope: str


def create_rest_app(rt: TrilithRuntime) -> FastAPI:
    app = FastAPI(
        title="Trilith Context Management API",
        description="Language-agnostic context management layer for AI systems.",
        version="0.1.0",
    )

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "trilith-core"}

    @app.post("/v1/write")
    def write(body: WriteBody):
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
        )
        ack = write_item(rt, item)
        if not ack.success:
            raise HTTPException(status_code=400, detail=ack.message)
        return {"success": True, "id": body.id}

    @app.post("/v1/assemble")
    def assemble(body: AssembleBody):
        assembled = rt.governor.assemble(
            task=body.task,
            budget=body.budget,
            requester_scope=body.requester_scope,
        )
        return {
            "items": [
                {"id": i.id, "tier": Tier.Name(i.tier), "content": i.content}
                for i in assembled.items
            ],
            "tokens_used": assembled.tokens_used,
            "excluded_items": [
                {"id": ex.item.id, "reason": ex.reason}
                for ex in assembled.excluded_items
            ],
        }

    @app.post("/v1/forget")
    def forget(body: ForgetBody):
        count = forget_scope(rt, body.scope)
        return {"success": True, "deleted_episodic_count": count}

    return app
