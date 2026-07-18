"""gRPC server bootstrap for trilith serve."""

from __future__ import annotations

from concurrent import futures
from typing import Tuple

import grpc

from core.grpc_servicer import TrilithServicer
from core.proto import trilith_pb2_grpc
from core.runtime import TrilithRuntime


def create_grpc_server(
    rt: TrilithRuntime,
    host: str,
    port: int,
    max_workers: int = 4,
) -> Tuple[grpc.Server, int]:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=max_workers))
    trilith_pb2_grpc.add_ContextManagerServicer_to_server(TrilithServicer(rt), server)
    bound = server.add_insecure_port(f"{host}:{port}")
    if bound == 0:
        raise RuntimeError(f"Failed to bind gRPC on {host}:{port}")
    return server, bound
