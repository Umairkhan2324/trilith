import time

from google.protobuf.timestamp_pb2 import Timestamp

from core.episodic import EpisodicStore
from core.privacy import PolicyEngine
from core.procedural import ProceduralStore
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.semantic import SemanticStore
from core.sqlite_backend import SQLiteBackend


def create_item(item_id, tier, scope, content="Hello!", expires_s=None):
    created = Timestamp()
    created.GetCurrentTime()
    
    expires = None
    if expires_s is not None:
        expires = Timestamp(seconds=int(expires_s), nanos=0)
        
    return ContextItem(
        id=item_id,
        tier=tier,
        scope=scope,
        content=content,
        provenance="testing",
        created_at=created,
        expires_at=expires
    )

def test_policy_engine_scope_matching():
    pe = PolicyEngine()
    item_global = create_item("glob", Tier.SEMANTIC, Scope.GLOBAL, "global fact")
    item_user = create_item("usr", Tier.SEMANTIC, Scope.USER, "user secret")
    
    # 1. Requester without scope (anonymous query)
    allowed, denied = pe.filter([item_global, item_user], requester_scope="")
    assert len(allowed) == 1
    assert allowed[0].id == "glob"
    assert len(denied) == 1
    assert denied[0][0].id == "usr"
    assert "Scope mismatch" in denied[0][1]

    # 2. Requester matching USER scope
    allowed, denied = pe.filter([item_global, item_user], requester_scope="USER")
    assert len(allowed) == 2
    assert len(denied) == 0

def test_policy_engine_pii_redaction():
    pe = PolicyEngine()
    content = "Email: john.doe@example.com, Phone: +1-555-666-7777, SSN: 123-45-6789."
    item = create_item("pii-item", Tier.SEMANTIC, Scope.GLOBAL, content)
    
    allowed, denied = pe.filter([item], requester_scope="")
    assert len(allowed) == 1
    redacted_content = allowed[0].content
    assert "john.doe@example.com" not in redacted_content
    assert "+1-555-666-7777" not in redacted_content
    assert "123-45-6789" not in redacted_content
    assert "[REDACTED_EMAIL]" in redacted_content
    assert "[REDACTED_PHONE]" in redacted_content
    assert "[REDACTED_ID]" in redacted_content

def test_policy_engine_expiry():
    pe = PolicyEngine()
    now = time.time()
    
    # Expired 5 seconds ago
    item_expired = create_item("old", Tier.SEMANTIC, Scope.GLOBAL, "olde content", expires_s=now - 5)
    # Expires in 60 seconds
    item_valid = create_item("new", Tier.SEMANTIC, Scope.GLOBAL, "fresh content", expires_s=now + 60)
    
    allowed, denied = pe.filter([item_expired, item_valid], requester_scope="")
    assert len(allowed) == 1
    assert allowed[0].id == "new"
    assert len(denied) == 1
    assert denied[0][0].id == "old"
    assert "expired" in denied[0][1]

def test_forget_cascade_deletes_physically():
    backend = SQLiteBackend()  # Shared database backend
    
    sem = SemanticStore(backend)
    proc = ProceduralStore(backend)
    epi = EpisodicStore(backend)
    
    # 1. Save data across all three tiers for scope TENANT
    # Scope.TENANT maps to int 2
    item_sem = create_item("sem-1", Tier.SEMANTIC, Scope.TENANT, "semantic business data")
    item_proc = create_item("proc-1", Tier.PROCEDURAL, Scope.TENANT, "procedural step data")
    item_epi = create_item("epi-1", Tier.EPISODIC, Scope.TENANT, "episodic chat history")
    
    sem.write(item_sem)
    proc.write(item_proc)
    epi.write(item_epi)
    
    # Verify they exist
    assert len(sem.query(scope="TENANT")) == 1
    assert len(proc.query(scope="TENANT")) == 1
    assert len(epi.query(scope="TENANT")) == 1
    
    # 2. Assert they are physically stored in the database
    cursor = backend._conn.cursor()
    cursor.execute("SELECT id FROM context_items WHERE scope = ?", (int(Scope.TENANT),))
    rows_before = cursor.fetchall()
    assert len(rows_before) == 3
    
    # 3. Call Forget cascading to sem and proc
    deleted = epi.forget(scope="TENANT", notify_stores=[sem, proc])
    assert deleted == 1
    
    # 4. Subsequent queries return nothing across all tiers
    assert len(sem.query(scope="TENANT")) == 0
    assert len(proc.query(scope="TENANT")) == 0
    assert len(epi.query(scope="TENANT")) == 0
    
    # 5. Assert database row count for scope TENANT is physically 0 (not just hidden by a flag)
    cursor.execute("SELECT id FROM context_items WHERE scope = ?", (int(Scope.TENANT),))
    rows_after = cursor.fetchall()
    assert len(rows_after) == 0
