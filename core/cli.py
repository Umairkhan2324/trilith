"""trilith CLI — serve the REST + gRPC gateways and manage tenant API keys."""

from __future__ import annotations

import argparse
import sys
import threading
from datetime import datetime, timezone


def _runtime(args):
    from core.runtime import build_runtime

    return build_runtime(args.db, require_auth=getattr(args, "require_auth", None))


def cmd_serve(args):
    try:
        import uvicorn
    except ImportError:
        print("ERROR: install server extras: pip install 'trilith-core[server]'")
        sys.exit(1)

    from core.grpc_server import create_grpc_server
    from core.rest_app import create_rest_app

    rt = _runtime(args)
    app = create_rest_app(rt)
    grpc_server, grpc_bound = create_grpc_server(rt, args.host, args.grpc_port)

    def run_rest():
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")

    threading.Thread(target=run_rest, daemon=True).start()
    grpc_server.start()

    print(f"[trilith serve] db={rt.db_path}")
    print(f"[trilith serve] REST  http://{args.host}:{args.port}")
    print(f"[trilith serve] gRPC  {args.host}:{grpc_bound}")

    if rt.auth.enabled:
        print("[trilith serve] auth  ENABLED — send 'Authorization: Bearer tri_...'")
    else:
        print("[trilith serve] auth  DISABLED — every caller is tenant 'default'")
        if args.host not in ("127.0.0.1", "localhost", "::1"):
            print(
                f"[trilith serve] WARNING: bound to {args.host} with no auth. "
                "Anyone who can reach this port can read and delete all context. "
                "Run 'trilith key create --tenant <id>' to enable auth."
            )

    grpc_server.wait_for_termination()


def cmd_key_create(args):
    rt = _runtime(args)
    raw, record = rt.keys.create(
        tenant_id=args.tenant, owner_id=args.owner or "", name=args.name or ""
    )
    print("API key created. This is shown once and cannot be recovered:\n")
    print(f"  {raw}\n")
    print(f"  tenant      {record.tenant_id}")
    print(f"  owner       {record.owner_id or '(any)'}")
    print(f"  name        {record.name or '(unnamed)'}")
    print(f"  fingerprint {record.fingerprint}")
    print("\nAuth is now enforced on this database for every REST and gRPC call.")


def cmd_key_list(args):
    rt = _runtime(args)
    records = rt.keys.list(tenant_id=args.tenant)
    if not records:
        print("No API keys. Auth is disabled; all callers are tenant 'default'.")
        return
    print(f"{'FINGERPRINT':<14} {'TENANT':<16} {'OWNER':<14} {'STATUS':<9} {'CREATED':<20} NAME")
    for r in records:
        created = datetime.fromtimestamp(r.created_at, tz=timezone.utc).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        status = "revoked" if r.revoked else "active"
        print(
            f"{r.fingerprint:<14} {r.tenant_id:<16} {(r.owner_id or '-'):<14} "
            f"{status:<9} {created:<20} {r.name}"
        )


def cmd_key_revoke(args):
    rt = _runtime(args)
    count = rt.keys.revoke(args.fingerprint)
    if count == 0:
        print(f"No active key matching fingerprint '{args.fingerprint}'.")
        sys.exit(1)
    print(f"Revoked {count} key(s) matching '{args.fingerprint}'.")


def cmd_tenants(args):
    rt = _runtime(args)
    tenants = rt.backend.list_tenants()
    if not tenants:
        print("No context items stored yet.")
        return
    from core.identity import Principal
    from core.proto.trilith_pb2 import Tier

    print(f"{'TENANT':<20} {'SEMANTIC':>9} {'PROCEDURAL':>11} {'EPISODIC':>9}")
    for tenant in tenants:
        p = Principal(tenant_id=tenant)
        counts = [
            rt.backend.count(tier, tenant_id=p.tenant_id)
            for tier in (Tier.SEMANTIC, Tier.PROCEDURAL, Tier.EPISODIC)
        ]
        print(f"{tenant:<20} {counts[0]:>9} {counts[1]:>11} {counts[2]:>9}")


def cmd_purge_expired(args):
    rt = _runtime(args)
    deleted = rt.backend.purge_expired(tenant_id=args.tenant or None)
    scope_label = args.tenant or "all tenants"
    print(f"Deleted {deleted} expired item(s) from {scope_label}.")


def _add_db_arg(parser):
    parser.add_argument("--db", default=None, help="SQLite path (or TRILITH_DB_PATH)")


def main():
    parser = argparse.ArgumentParser(
        prog="trilith",
        description="Trilith — context management layer for AI systems",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Start REST + gRPC context servers")
    serve.add_argument("--host", default="127.0.0.1", help="Bind host (default: localhost)")
    serve.add_argument("--port", type=int, default=8080, help="REST port")
    serve.add_argument("--grpc-port", type=int, default=50051, help="gRPC port")
    serve.add_argument(
        "--require-auth",
        action="store_true",
        default=None,
        help="Reject unauthenticated calls even before any key is minted",
    )
    _add_db_arg(serve)

    key = sub.add_parser("key", help="Manage tenant API keys")
    key_sub = key.add_subparsers(dest="key_command")

    key_create = key_sub.add_parser("create", help="Mint an API key bound to a tenant")
    key_create.add_argument("--tenant", required=True, help="Tenant this key acts as")
    key_create.add_argument("--owner", default="", help="Pin the key to one owner/user id")
    key_create.add_argument("--name", default="", help="Label for your own reference")
    _add_db_arg(key_create)

    key_list = key_sub.add_parser("list", help="List API keys (never shows the secret)")
    key_list.add_argument("--tenant", default=None, help="Filter by tenant")
    _add_db_arg(key_list)

    key_revoke = key_sub.add_parser("revoke", help="Revoke a key by fingerprint prefix")
    key_revoke.add_argument("fingerprint", help="Fingerprint or unique prefix")
    _add_db_arg(key_revoke)

    tenants = sub.add_parser("tenants", help="List tenants and their item counts")
    _add_db_arg(tenants)

    purge = sub.add_parser("purge-expired", help="Physically delete items past their TTL")
    purge.add_argument("--tenant", default=None, help="Limit to one tenant")
    _add_db_arg(purge)

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "key":
        handlers = {
            "create": cmd_key_create,
            "list": cmd_key_list,
            "revoke": cmd_key_revoke,
        }
        handler = handlers.get(args.key_command)
        if handler is None:
            key.print_help()
            sys.exit(0)
        handler(args)
    elif args.command == "tenants":
        cmd_tenants(args)
    elif args.command == "purge-expired":
        cmd_purge_expired(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
