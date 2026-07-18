"""Shared write/query/forget operations used by REST and gRPC gateways."""

from __future__ import annotations

from typing import List

from google.protobuf.timestamp_pb2 import Timestamp

from core.proto.trilith_pb2 import ContextItem, QueryResponse, Tier, WriteAck
from core.runtime import TrilithRuntime


def ensure_created_at(item: ContextItem) -> None:
    if not item.HasField("created_at"):
        ts = Timestamp()
        ts.GetCurrentTime()
        item.created_at.CopyFrom(ts)


def write_item(rt: TrilithRuntime, item: ContextItem) -> WriteAck:
    ensure_created_at(item)
    if item.tier == Tier.SEMANTIC:
        rt.semantic.write(item)
    elif item.tier == Tier.PROCEDURAL:
        rt.procedural.write(item)
    elif item.tier == Tier.EPISODIC:
        rt.episodic.write(item)
    else:
        return WriteAck(success=False, message="Invalid or unspecified tier")
    return WriteAck(success=True, message=f"Wrote {item.id}")


def query_items(
    rt: TrilithRuntime,
    tier: Tier,
    filter_text: str = "",
    budget_tokens: int = 0,
    scope: str = "",
) -> QueryResponse:
    store = {
        Tier.SEMANTIC: rt.semantic,
        Tier.PROCEDURAL: rt.procedural,
        Tier.EPISODIC: rt.episodic,
    }.get(tier)
    if store is None:
        return QueryResponse(items=[])
    items: List[ContextItem] = store.query(
        filter=filter_text,
        budget_tokens=budget_tokens,
        scope=scope,
    )
    return QueryResponse(items=items)


def forget_scope(rt: TrilithRuntime, scope: str) -> int:
    return rt.episodic.forget(
        scope=scope,
        notify_stores=[rt.semantic, rt.procedural],
    )
