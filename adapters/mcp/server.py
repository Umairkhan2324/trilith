"""MCP server exposing Trilith's context operations as tools.

An MCP host is a single trusted process, so this adapter does not use API
keys. Tenancy is still real: every tool takes a `tenant_id`, defaulting to
`default`, so one host can serve several isolated workspaces from one database.
"""

import json
import os
import sys

# Ensure core is in python path if run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from google.protobuf.timestamp_pb2 import Timestamp  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402

from core.identity import Principal  # noqa: E402
from core.ops import fold_subtask, forget_scope, purge_expired, write_item  # noqa: E402
from core.proto.trilith_pb2 import ContextItem, Scope, Tier  # noqa: E402
from core.runtime import build_runtime  # noqa: E402

# Share the same wiring as REST and gRPC: one runtime, thread-safe backend,
# automatic schema migration, expired-item reaping on startup.
DB_FILE = os.environ.get("TRILITH_DB_PATH", "trilith_mcp.db")
rt = build_runtime(DB_FILE)

mcp = FastMCP("Trilith")


def _principal(tenant_id: str = "", owner_id: str = "", session_id: str = "") -> Principal:
    return Principal(tenant_id=tenant_id, owner_id=owner_id, session_id=session_id)


@mcp.tool()
def write_context(
    id: str,
    tier: str,
    content: str,
    scope: str,
    provenance: str = "",
    tenant_id: str = "default",
    owner_id: str = "",
    session_id: str = "",
) -> str:
    """Writes a context item into Trilith.

    Args:
        id: Unique identifier for the item
        tier: One of 'SEMANTIC', 'PROCEDURAL', or 'EPISODIC'
        content: The text content to store
        scope: Visibility within the tenant — 'USER', 'TENANT', 'SESSION', or 'GLOBAL'
        provenance: Origin description of the item
        tenant_id: Isolation boundary this item belongs to
        owner_id: User this item belongs to (required for USER scope to isolate)
        session_id: Session this item belongs to (required for SESSION scope)
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
        created_at=created,
        owner_id=owner_id,
        session_id=session_id,
    )

    ack = write_item(rt, item, principal=_principal(tenant_id, owner_id, session_id))
    if not ack.success:
        return f"Error: {ack.message}"
    return f"Success: Wrote item {id} to {tier.upper()} tier in tenant '{item.tenant_id}'."


@mcp.tool()
def assemble_context(
    task: str,
    budget: int = 200,
    tenant_id: str = "default",
    owner_id: str = "",
    session_id: str = "",
) -> str:
    """Retrieves and assembles context for a task within a token budget.

    Returns included items plus every excluded item and the reason it was cut.

    Args:
        task: Description of the task/query
        budget: Maximum tokens allowed (estimate)
        tenant_id: Isolation boundary to read from
        owner_id: Unlocks USER-scoped items belonging to this owner
        session_id: Unlocks SESSION-scoped items belonging to this session
    """
    try:
        assembled = rt.governor.assemble(
            task, budget, principal=_principal(tenant_id, owner_id, session_id)
        )
    except Exception as e:
        return f"Assembly error: {str(e)}"

    result = {
        "items": [
            {"id": item.id, "tier": Tier.Name(item.tier), "content": item.content}
            for item in assembled.items
        ],
        "tokens_used": assembled.tokens_used,
        "excluded_items": [
            {"id": ex.item.id, "reason": ex.reason} for ex in assembled.excluded_items
        ],
        "candidates_truncated": assembled.candidates_truncated,
    }
    return json.dumps(result, indent=2)


@mcp.tool()
def fold_procedural(
    subtask_id: str,
    tenant_id: str = "default",
) -> str:
    """Collapses all procedural steps of a sub-task into one summary item.

    Use this when a multi-step task finishes, to stop its steps consuming
    budget on every later assemble.

    Args:
        subtask_id: The sub-task whose steps should be folded
        tenant_id: Isolation boundary the sub-task belongs to
    """
    try:
        summary, count = fold_subtask(rt, subtask_id, principal=_principal(tenant_id))
    except Exception as e:
        return f"Fold error: {str(e)}"

    if summary is None:
        return f"No procedural steps found for subtask '{subtask_id}' in tenant '{tenant_id}'."
    return f"Folded {count} steps into '{summary.id}'."


@mcp.tool()
def forget(
    scope: str,
    tenant_id: str = "default",
    owner_id: str = "",
    session_id: str = "",
) -> str:
    """Irrevocably purges memory of the given scope across all three tiers.

    Args:
        scope: The scope to purge — 'USER', 'TENANT', or 'SESSION'
        tenant_id: Isolation boundary to purge within
        owner_id: With scope USER, limits the purge to this owner
        session_id: With scope SESSION, limits the purge to this session
    """
    try:
        count = forget_scope(
            rt, scope, principal=_principal(tenant_id, owner_id, session_id)
        )
        return (
            f"Purged {count} episodic items of scope '{scope}' in tenant "
            f"'{tenant_id}', cascading to other tiers."
        )
    except Exception as e:
        return f"Forget error: {str(e)}"


# Kept under its v0.1 name so existing MCP host configs keep working.
@mcp.tool()
def forget_scope_tool(scope: str, tenant_id: str = "default") -> str:
    """Deprecated alias for `forget`. Purges a scope across all tiers."""
    return forget(scope=scope, tenant_id=tenant_id)


@mcp.tool()
def purge_expired_items(tenant_id: str = "default") -> str:
    """Physically deletes items whose TTL has passed.

    Args:
        tenant_id: Isolation boundary to reap within
    """
    deleted = purge_expired(rt, principal=_principal(tenant_id))
    return f"Deleted {deleted} expired item(s) from tenant '{tenant_id}'."


if __name__ == "__main__":
    mcp.run()
