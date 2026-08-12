"""LangChain / LangGraph plug-and-play tools and nodes."""

from __future__ import annotations

import json
from typing import Any, Callable, Optional

from core.client import TrilithClient


def _require_tool():
    try:
        from langchain_core.tools import tool
    except ImportError as exc:
        raise ImportError(
            "Install LangChain extras: pip install 'trilith-core[langchain]'"
        ) from exc
    return tool


def make_trilith_tools(client: TrilithClient | None = None) -> list[Any]:
    """Return LangChain tools: write / assemble / fold / forget.

    Bind identity on the client, not on the tools — an agent should not be able
    to talk itself into another tenant:

        client = TrilithClient(api_key="tri_...", owner_id="alice")
        tools = make_trilith_tools(client)
    """
    tool = _require_tool()
    c = client or TrilithClient()

    @tool
    def trilith_write(
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "TENANT",
    ) -> str:
        """Store a durable fact or event in Trilith memory."""
        return json.dumps(c.write(id=id, content=content, tier=tier, scope=scope))

    @tool
    def trilith_assemble(task: str, budget: int = 300) -> str:
        """Fetch budgeted, ranked context for a task before calling the LLM."""
        return json.dumps(c.assemble(task, budget=budget))

    @tool
    def trilith_fold(subtask_id: str) -> str:
        """Collapse a finished sub-task's procedural steps into one summary."""
        return json.dumps(c.fold(subtask_id))

    @tool
    def trilith_forget(scope: str) -> str:
        """Physically purge Trilith memory for a scope within your tenant."""
        return json.dumps(c.forget(scope))

    return [trilith_write, trilith_assemble, trilith_fold, trilith_forget]


def make_assemble_node(
    client: TrilithClient | None = None,
    input_key: str = "input",
    budget: int = 400,
    session_key: Optional[str] = "session_id",
) -> Callable[[dict], dict]:
    """LangGraph node: state[input_key] → trilith_memory + trilith_context.

    If `session_key` names a field in the graph state, its value is used as the
    session identity for the call — so a graph serving many concurrent
    conversations keeps their SESSION-scoped memory apart.
    """
    c = client or TrilithClient()

    def assemble_node(state: dict) -> dict:
        task = state.get(input_key) or ""
        if not task and state.get("messages"):
            last = state["messages"][-1]
            task = getattr(last, "content", None) or str(last)

        identity = {}
        if session_key and state.get(session_key):
            identity["session_id"] = str(state[session_key])

        ctx = c.assemble(str(task), budget=budget, **identity)
        memory = "\n".join(f"- {i.get('content', '')}" for i in (ctx.get("items") or []))
        return {
            **state,
            "trilith_context": ctx,
            "trilith_memory": memory,
        }

    return assemble_node
