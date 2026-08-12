"""gRPC ContextManager servicer backed by TrilithRuntime."""

from __future__ import annotations

from typing import Optional

import grpc

from core.auth import AuthError
from core.identity import Principal
from core.ops import fold_subtask, forget_scope, purge_expired, query_items, write_item
from core.proto import trilith_pb2, trilith_pb2_grpc
from core.runtime import TrilithRuntime


class TrilithServicer(trilith_pb2_grpc.ContextManagerServicer):
    def __init__(self, rt: TrilithRuntime):
        self._rt = rt

    @staticmethod
    def _authorization(context) -> Optional[str]:
        for key, value in context.invocation_metadata() or ():
            if key.lower() == "authorization":
                return value
        return None

    def _principal(
        self,
        request,
        context,
        legacy_scope: str = "",
    ) -> Optional[Principal]:
        """Resolve the caller, or abort with UNAUTHENTICATED."""
        pb = request.principal if request.HasField("principal") else None
        supplied = Principal.from_pb(pb, legacy_scope=legacy_scope)
        try:
            return self._rt.auth.resolve(
                self._authorization(context),
                tenant_id=pb.tenant_id if pb else "",
                owner_id=supplied.owner_id,
                session_id=supplied.session_id,
                legacy_scope=supplied.legacy_scope,
            )
        except AuthError as exc:
            context.abort(grpc.StatusCode.UNAUTHENTICATED, str(exc))
            return None

    def Write(self, request, context):
        if not request.HasField("item"):
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("WriteRequest.item is required")
            return trilith_pb2.WriteAck(success=False, message="missing item")
        principal = self._principal(request, context)
        return write_item(self._rt, request.item, principal=principal)

    def Query(self, request, context):
        principal = self._principal(request, context, legacy_scope=request.scope)
        try:
            return query_items(
                self._rt,
                tier=request.tier,
                filter_text=request.filter,
                budget_tokens=request.budget_tokens,
                scope=request.scope,
                principal=principal,
            )
        except (ValueError, KeyError) as exc:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details(str(exc))
            return trilith_pb2.QueryResponse()

    def Assemble(self, request, context):
        principal = self._principal(
            request, context, legacy_scope=request.requester_scope
        )
        return self._rt.governor.assemble(
            task=request.task_description,
            budget=request.budget_tokens,
            principal=principal,
        )

    def Forget(self, request, context):
        if not request.scope:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("ForgetRequest.scope is required")
            return trilith_pb2.ForgetAck(success=False, message="missing scope")
        principal = self._principal(request, context)
        count = forget_scope(self._rt, request.scope, principal=principal)
        return trilith_pb2.ForgetAck(
            success=True,
            message=f"Purged scope '{request.scope}' (episodic deleted={count})",
            deleted_count=count,
        )

    def Fold(self, request, context):
        if not request.subtask_id:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("FoldRequest.subtask_id is required")
            return trilith_pb2.FoldResponse(success=False, message="missing subtask_id")
        principal = self._principal(request, context)
        summary, folded_count = fold_subtask(
            self._rt, request.subtask_id, principal=principal
        )
        if summary is None:
            return trilith_pb2.FoldResponse(
                success=False,
                message=f"No procedural steps found for subtask '{request.subtask_id}'",
                folded_count=0,
            )
        return trilith_pb2.FoldResponse(
            success=True,
            message=f"Folded {folded_count} steps",
            item=summary,
            folded_count=folded_count,
        )

    def PurgeExpired(self, request, context):
        principal = self._principal(request, context)
        deleted = purge_expired(self._rt, principal=principal)
        return trilith_pb2.PurgeExpiredResponse(success=True, deleted_count=deleted)
