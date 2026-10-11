"""MCP server exposing Trilith's context operations as tools.

Identity comes from host environment, never model-controlled tool arguments.
Use one stdio process per tenant/owner/session. No admin or publisher capability.
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


def _principal() -> Principal:
    return Principal(
        tenant_id=os.environ.get("TRILITH_TENANT_ID", "default"),
        owner_id=os.environ.get("TRILITH_OWNER_ID", ""),
        session_id=os.environ.get("TRILITH_SESSION_ID", ""),
        authenticated=True,
    )


@mcp.tool()
def write_context(
    id: str,
    tier: str,
    content: str,
    scope: str,
    provenance: str = "",
) -> str:
    """Writes a context item into Trilith.

    Args:
        id: Unique identifier for the item
        tier: One of 'SEMANTIC', 'PROCEDURAL', or 'EPISODIC'
        content: The text content to store
        scope: Visibility within the tenant — 'USER', 'TENANT', 'SESSION', or 'GLOBAL'
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
        created_at=created,
        owner_id=_principal().owner_id,
        session_id=_principal().session_id,
    )

    ack = write_item(rt, item, principal=_principal())
    if not ack.success:
        return f"Error: {ack.message}"
    return f"Success: Wrote item {id} to {tier.upper()} tier in tenant '{item.tenant_id}'."


@mcp.tool()
def assemble_context(
    task: str,
    budget: int = 200,
) -> str:
    """Retrieves and assembles context for a task within a token budget.

    Returns included items plus every excluded item and the reason it was cut.

    Args:
        task: Description of the task/query
        budget: Maximum tokens allowed (estimate)
    """
    try:
        assembled = rt.governor.assemble(task, budget, principal=_principal())
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
) -> str:
    """Collapses all procedural steps of a sub-task into one summary item.

    Use this when a multi-step task finishes, to stop its steps consuming
    budget on every later assemble.

    Args:
        subtask_id: The sub-task whose steps should be folded
    """
    try:
        summary, count = fold_subtask(rt, subtask_id, principal=_principal())
    except Exception as e:
        return f"Fold error: {str(e)}"

    if summary is None:
        return f"No procedural steps found for subtask '{subtask_id}' in tenant '{_principal().tenant_id}'."
    return f"Folded {count} steps into '{summary.id}'."


@mcp.tool()
def forget(
    scope: str,
) -> str:
    """Irrevocably purges memory of the given scope across all three tiers.

    Args:
        scope: The scope to purge — 'USER', 'TENANT', or 'SESSION'
    """
    try:
        count = forget_scope(rt, scope, principal=_principal())
        return (
            f"Purged {count} episodic items of scope '{scope}' in tenant "
            f"'{_principal().tenant_id}', cascading to other tiers."
        )
    except Exception as e:
        return f"Forget error: {str(e)}"


# Kept under its v0.1 name so existing MCP host configs keep working.
@mcp.tool()
def forget_scope_tool(scope: str) -> str:
    """Deprecated alias for `forget`. Purges a scope across all tiers."""
    return forget(scope=scope)


@mcp.tool()
def purge_expired_items() -> str:
    """Physically deletes items whose TTL has passed.

    Args:
    """
    deleted = purge_expired(rt, principal=_principal())
    return f"Deleted {deleted} expired item(s) from tenant '{_principal().tenant_id}'."


if __name__ == "__main__":
    mcp.run()
