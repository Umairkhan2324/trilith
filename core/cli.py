"""trilith CLI — `trilith serve` starts REST + gRPC on one shared runtime."""

from __future__ import annotations

import argparse
import sys
import threading


def cmd_serve(args):
    try:
        import uvicorn
    except ImportError:
        print("ERROR: install server extras: pip install 'trilith-core[server]'")
        sys.exit(1)

    from core.grpc_server import create_grpc_server
    from core.rest_app import create_rest_app
    from core.runtime import build_runtime

    rt = build_runtime(args.db)
    app = create_rest_app(rt)
    grpc_server, grpc_bound = create_grpc_server(rt, args.host, args.grpc_port)

    def run_rest():
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")

    threading.Thread(target=run_rest, daemon=True).start()
    grpc_server.start()
    print(f"[trilith serve] db={rt.db_path}")
    print(f"[trilith serve] REST  http://{args.host}:{args.port}")
    print(f"[trilith serve] gRPC  {args.host}:{grpc_bound}")
    grpc_server.wait_for_termination()


def main():
    parser = argparse.ArgumentParser(
        prog="trilith",
        description="Trilith — context management layer for AI systems",
    )
    sub = parser.add_subparsers(dest="command")
    serve = sub.add_parser("serve", help="Start REST + gRPC context servers")
    serve.add_argument("--host", default="0.0.0.0")
    serve.add_argument("--port", type=int, default=8080, help="REST port")
    serve.add_argument("--grpc-port", type=int, default=50051, help="gRPC port")
    serve.add_argument("--db", default=None, help="SQLite path (or TRILITH_DB_PATH)")

    args = parser.parse_args()
    if args.command == "serve":
        cmd_serve(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
