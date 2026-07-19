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
    """Return OpenAI Agents function tools bound to a TrilithClient."""
    function_tool = _require_function_tool()
    c = client or TrilithClient()

    @function_tool
    def trilith_write(
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "USER",
    ) -> str:
        """Store a durable fact or event in Trilith memory."""
        return json.dumps(c.write(id=id, content=content, tier=tier, scope=scope))

    @function_tool
    def trilith_assemble(
        task: str,
        budget: int = 300,
        requester_scope: str = "USER",
    ) -> str:
        """Fetch budgeted, ranked context for the current task."""
        return json.dumps(c.assemble(task, budget=budget, requester_scope=requester_scope))

    @function_tool
    def trilith_forget(scope: str) -> str:
        """Physically purge all Trilith memory for a scope."""
        return json.dumps(c.forget(scope))

    return [trilith_write, trilith_assemble, trilith_forget]
