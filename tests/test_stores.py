import pytest
from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.sqlite_backend import SQLiteBackend
from core.semantic import SemanticStore
from core.procedural import ProceduralStore
from core.episodic import EpisodicStore
from google.protobuf.timestamp_pb2 import Timestamp

def create_item(item_id, tier, scope, content="Test contents"):
    created = Timestamp()
    created.GetCurrentTime()
    return ContextItem(
        id=item_id,
        tier=tier,
        scope=scope,
        content=content,
        provenance="tests",
        created_at=created
    )

def test_semantic_store():
    backend = SQLiteBackend()  # in-memory
    sem = SemanticStore(backend)
    
    item = create_item("semi-1", Tier.SEMANTIC, Scope.USER, "semantic context content")
    assert sem.write(item) is True
    
    # Query with USER scope
    items = sem.query(scope="USER")
    assert len(items) == 1
    assert items[0].id == "semi-1"
    
    # Query all (no scope filter)
    all_items = sem.query()
    assert len(all_items) == 1

def test_procedural_store_folding():
    backend = SQLiteBackend()
    proc = ProceduralStore(backend)
    
    # Write items under the same subtask_id
    item1 = create_item("step-1", Tier.PROCEDURAL, Scope.GLOBAL, "Initial setup")
    item2 = create_item("step-2", Tier.PROCEDURAL, Scope.GLOBAL, "Core build step")
    
    assert proc.write(item1, subtask_id="task-123") is True
    assert proc.write(item2, subtask_id="task-123") is True
    
    # Query before fold
    items_before = proc.query()
    assert len(items_before) == 2
    
    # Fold it
    folded = proc.fold(subtask_id="task-123")
    assert folded is not None
    assert folded.id == "folded-task-123"
    assert "Initial setup" in folded.content
    assert "Core build step" in folded.content
    
    # Query after fold: only the summary item should remain
    items_after = proc.query()
    assert len(items_after) == 1
    assert items_after[0].id == "folded-task-123"

def test_episodic_store_scope_enforcement():
    backend = SQLiteBackend()
    epi = EpisodicStore(backend)
    
    item = create_item("epi-1", Tier.EPISODIC, Scope.TENANT, "episodic secret details")
    assert epi.write(item) is True
    
    # Query without scope should raise ValueError
    with pytest.raises(ValueError, match="must specify a valid scope"):
        epi.query(scope="")
        
    # Query with GLOBAL or UNSPECIFIED scope should raise KeyError
    with pytest.raises(KeyError, match="cannot use UNSPECIFIED or GLOBAL scope"):
        epi.query(scope="GLOBAL")
        
    # Query with matching TENANT scope
    results = epi.query(scope="TENANT")
    assert len(results) == 1
    assert results[0].id == "epi-1"

def test_episodic_forget_cascade():
    backend = SQLiteBackend()
    
    sem = SemanticStore(backend)
    proc = ProceduralStore(backend)
    epi = EpisodicStore(backend)
    
    # Insert items with USER scope to all three tiers
    item_sem = create_item("semi", Tier.SEMANTIC, Scope.USER)
    item_proc = create_item("proc", Tier.PROCEDURAL, Scope.USER)
    item_epi = create_item("epi", Tier.EPISODIC, Scope.USER)
    
    sem.write(item_sem)
    proc.write(item_proc)
    epi.write(item_epi)
    
    # Verify they were saved
    assert len(sem.query(scope="USER")) == 1
    assert len(proc.query(scope="USER")) == 1
    assert len(epi.query(scope="USER")) == 1
    
    # Run forget and verify cascade delete
    deleted_count = epi.forget(scope="USER", notify_stores=[sem, proc])
    assert deleted_count == 1
    
    # Both Episodic store and Semantic/Procedural stores should have these deleted
    assert len(epi.query(scope="USER")) == 0
    assert len(sem.query(scope="USER")) == 0
    assert len(proc.query(scope="USER")) == 0
