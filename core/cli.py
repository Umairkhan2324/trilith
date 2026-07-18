"""
trilith CLI entrypoint — `trilith serve`
Starts a FastAPI + gRPC compatible context server backed by SQLite.
"""

import argparse
import sys
import os


def cmd_serve(args):
    """Start the Trilith context management server."""
    try:
        import uvicorn
    except ImportError:
        print("ERROR: uvicorn is required to run the server. Install with:")
        print("  pip install 'trilith-core[server]'")
        sys.exit(1)

    from core.sqlite_backend import SQLiteBackend
    from core.semantic import SemanticStore
    from core.procedural import ProceduralStore
    from core.episodic import EpisodicStore
    from core.privacy import PolicyEngine
    from core.governor import Governor
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    from typing import Optional
    from core.proto.trilith_pb2 import ContextItem, Tier, Scope
    from google.protobuf.timestamp_pb2 import Timestamp

    db_path = args.db or os.environ.get("TRILITH_DB_PATH", "trilith.db")
    print(f"[trilith serve] Using database: {db_path}")

    backend = SQLiteBackend(db_path)
    sem = SemanticStore(backend)
    proc = ProceduralStore(backend)
    epi = EpisodicStore(backend)
    policy = PolicyEngine()
    gov = Governor(
        semantic_store=sem,
        procedural_store=proc,
        episodic_store=epi,
        policy_engine=policy,
    )

    app = FastAPI(
        title="Trilith Context Management API",
        description="Language-agnostic context management layer for AI systems.",
        version="0.1.0",
    )

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

    @app.get("/healthz")
    def health():
        return {"status": "ok", "service": "trilith-core"}

    @app.post("/v1/write")
    def write(body: WriteBody):
        try:
            tier_enum = Tier.Value(body.tier.upper())
            scope_enum = Scope.Value(body.scope.upper())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

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
        if tier_enum == Tier.SEMANTIC:
            sem.write(item)
        elif tier_enum == Tier.PROCEDURAL:
            proc.write(item)
        elif tier_enum == Tier.EPISODIC:
            epi.write(item)
        return {"success": True, "id": body.id}

    @app.post("/v1/assemble")
    def assemble(body: AssembleBody):
        assembled = gov.assemble(
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
        count = epi.forget(scope=body.scope, notify_stores=[sem, proc])
        return {"success": True, "deleted_episodic_count": count}

    print(f"[trilith serve] Listening on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port)


def main():
    parser = argparse.ArgumentParser(
        prog="trilith",
        description="Trilith — context management layer for AI systems",
    )
    sub = parser.add_subparsers(dest="command")

    serve_parser = sub.add_parser("serve", help="Start the Trilith HTTP context server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8080, help="Bind port (default: 8080)")
    serve_parser.add_argument("--db", default=None, help="Path to SQLite DB file (default: trilith.db)")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
