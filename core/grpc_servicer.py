"""gRPC ContextManager servicer backed by TrilithRuntime."""

from __future__ import annotations

import grpc

from core.ops import forget_scope, query_items, write_item
from core.proto import trilith_pb2, trilith_pb2_grpc
from core.runtime import TrilithRuntime


class TrilithServicer(trilith_pb2_grpc.ContextManagerServicer):
    def __init__(self, rt: TrilithRuntime):
        self._rt = rt

    def Write(self, request, context):
        if not request.HasField("item"):
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("WriteRequest.item is required")
            return trilith_pb2.WriteAck(success=False, message="missing item")
        return write_item(self._rt, request.item)

    def Query(self, request, context):
        try:
            return query_items(
                self._rt,
                tier=request.tier,
                filter_text=request.filter,
                budget_tokens=request.budget_tokens,
                scope=request.scope,
            )
        except (ValueError, KeyError) as exc:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(exc))
            return trilith_pb2.QueryResponse()

    def Assemble(self, request, context):
        return self._rt.governor.assemble(
            task=request.task_description,
            budget=request.budget_tokens,
            requester_scope=request.requester_scope,
        )

    def Forget(self, request, context):
        if not request.scope:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("ForgetRequest.scope is required")
            return trilith_pb2.ForgetAck(success=False, message="missing scope")
        count = forget_scope(self._rt, request.scope)
        return trilith_pb2.ForgetAck(
            success=True,
            message=f"Purged scope '{request.scope}' (episodic deleted={count})",
        )
