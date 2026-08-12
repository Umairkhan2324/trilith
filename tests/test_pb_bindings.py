import pytest
from google.protobuf.timestamp_pb2 import Timestamp

from core.proto.trilith_pb2 import (
    AssembledContext,
    ContextItem,
    ExcludedItem,
    Scope,
    Tier,
)


def test_context_item_serialization():
    created = Timestamp()
    created.GetCurrentTime()
    
    expires = Timestamp()
    expires.FromSeconds(int(created.seconds) + 3600)
    
    item = ContextItem(
        id="test-1",
        tier=Tier.SEMANTIC,
        content="This is semantic memory content.",
        scope=Scope.USER,
        provenance="test_provenance",
        created_at=created,
        expires_at=expires,
        embedding=[0.1, 0.2, 0.3]
    )
    
    assert item.id == "test-1"
    assert item.tier == Tier.SEMANTIC
    assert item.content == "This is semantic memory content."
    assert item.scope == Scope.USER
    assert item.provenance == "test_provenance"
    assert item.created_at.seconds == created.seconds
    assert item.expires_at.seconds == expires.seconds
    assert list(item.embedding) == pytest.approx([0.1, 0.2, 0.3])

def test_assembled_context_serialization():
    item = ContextItem(
        id="test-2",
        tier=Tier.EPISODIC,
        content="This is episodic memory content.",
        scope=Scope.SESSION,
        provenance="test"
    )
    
    excluded = ExcludedItem(
        item=item,
        reason="Exceeded token budget"
    )
    
    assembled = AssembledContext(
        items=[item],
        tokens_used=150,
        excluded_items=[excluded]
    )
    
    assert len(assembled.items) == 1
    assert assembled.items[0].id == "test-2"
    assert assembled.tokens_used == 150
    assert len(assembled.excluded_items) == 1
    assert assembled.excluded_items[0].reason == "Exceeded token budget"
    assert assembled.excluded_items[0].item.id == "test-2"
