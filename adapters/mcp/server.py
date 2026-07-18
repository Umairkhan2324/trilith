import sys
import os
import json
from typing import Optional

# Ensure core is in python path if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from mcp.server.fastmcp import FastMCP
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from google.protobuf.timestamp_pb2 import Timestamp
from core.sqlite_backend import SQLiteBackend
from core.semantic import SemanticStore
from core.procedural import ProceduralStore
from core.episodic import EpisodicStore
from core.privacy import PolicyEngine
from core.governor import Governor

# Use a default file-based SQLite database for persistence
DB_FILE = os.environ.get("TRILITH_DB_PATH", "trilith_mcp.db")
backend = SQLiteBackend(DB_FILE)

sem_store = SemanticStore(backend)
proc_store = ProceduralStore(backend)
epi_store = EpisodicStore(backend)
policy_engine = PolicyEngine()
gov = Governor(sem_store, proc_store, epi_store, policy_engine)

mcp = FastMCP("Trilith")

@mcp.tool()
def write_context(
    id: str,
    tier: str,
    content: str,
    scope: str,
    provenance: str = ""
) -> str:
    """Writes a context item into Trilith.

    Args:
        id: Unique identifier for the item
        tier: One of 'SEMANTIC', 'PROCEDURAL', or 'EPISODIC'
        content: The text content to store
        scope: One of 'USER', 'TENANT', 'SESSION', or 'GLOBAL'
        provenance: Origin description of the item
    """
    try:
        tier_enum = Tier.Value(tier.upper())
        scope_enum = Scope.Value(scope.upper())
    except ValueError:
        valid_tiers = [Tier.Name(x) for x in Tier.values() if x != 0]
        valid_scopes = [Scope.Name(x) for x in Scope.values() if x != 0]
        return f"Error: Invalid tier or scope. Valid tiers: {valid_tiers}. Valid scopes: {valid_scopes}"

    created = Timestamp()
    created.GetCurrentTime()
    
    item = ContextItem(
        id=id,
        tier=tier_enum,
        scope=scope_enum,
        content=content,
        provenance=provenance,
        created_at=created
    )

    if tier_enum == Tier.SEMANTIC:
        sem_store.write(item)
    elif tier_enum == Tier.PROCEDURAL:
        proc_store.write(item)
    elif tier_enum == Tier.EPISODIC:
        epi_store.write(item)
        
    return f"Success: Wrote item {id} to {tier.upper()} tier."

@mcp.tool()
def assemble_context(
    task: str,
    budget: int = 200,
    requester_scope: str = "GLOBAL"
) -> str:
    """Retrieves and assembles context items matching a task description while respecting token budgets and privacy.

    Args:
        task: Description of the task/query
        budget: Maximum tokens allowed (estimate)
        requester_scope: The privacy scope of the requester (e.g. 'USER', 'TENANT', 'SESSION', 'GLOBAL')
    """
    try:
        assembled = gov.assemble(task, budget, requester_scope)
    except Exception as e:
        return f"Assembly error: {str(e)}"
        
    result = {
        "items": [{"id": item.id, "tier": Tier.Name(item.tier), "content": item.content} for item in assembled.items],
        "tokens_used": assembled.tokens_used,
        "excluded_items": [{"id": ex.item.id, "reason": ex.reason} for ex in assembled.excluded_items]
    }
    return json.dumps(result, indent=2)

@mcp.tool()
def forget_scope(scope: str) -> str:
    """Irrevocably purges all episodic memory of the specified scope and cascades deletions to semantic and procedural stores.

    Args:
        scope: The scope to purge (e.g. 'USER', 'TENANT', 'SESSION')
    """
    try:
        count = epi_store.forget(scope, notify_stores=[sem_store, proc_store])
        return f"Purged {count} episodic items of scope '{scope}', cascading to other tiers."
    except Exception as e:
        return f"Forget error: {str(e)}"

if __name__ == "__main__":
    mcp.run()
