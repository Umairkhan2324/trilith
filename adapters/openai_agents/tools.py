"""OpenAI Agents SDK plug-and-play Trilith tools."""

from __future__ import annotations

import json
from typing import Any

from core.client import TrilithClient


def _require_function_tool():
    try:
        from agents import function_tool
    except ImportError as exc:
        raise ImportError(
            "Install OpenAI Agents extras: pip install 'trilith-core[openai-agents]'"
        ) from exc
    return function_tool


def make_trilith_tools(client: TrilithClient | None = None) -> list[Any]:
    """Return OpenAI Agents function tools bound to a TrilithClient.

    Identity belongs on the client, so the model cannot choose its own tenant:

        client = TrilithClient(api_key="tri_...", owner_id="alice")
        tools = make_trilith_tools(client)
    """
    function_tool = _require_function_tool()
    c = client or TrilithClient()

    @function_tool
    def trilith_write(
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "TENANT",
    ) -> str:
        """Store a durable fact or event in Trilith memory."""
        return json.dumps(c.write(id=id, content=content, tier=tier, scope=scope))

    @function_tool
    def trilith_assemble(task: str, budget: int = 300) -> str:
        """Fetch budgeted, ranked context for the current task."""
        return json.dumps(c.assemble(task, budget=budget))

    @function_tool
    def trilith_fold(subtask_id: str) -> str:
        """Collapse a finished sub-task's procedural steps into one summary."""
        return json.dumps(c.fold(subtask_id))

    @function_tool
    def trilith_forget(scope: str) -> str:
        """Physically purge Trilith memory for a scope within your tenant."""
        return json.dumps(c.forget(scope))

    return [trilith_write, trilith_assemble, trilith_fold, trilith_forget]
