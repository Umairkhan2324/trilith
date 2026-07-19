"""LangChain / LangGraph plug-and-play tools and nodes."""

from __future__ import annotations

import json
from typing import Any, Callable

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
    """Return LangChain tools: write / assemble / forget."""
    tool = _require_tool()
    c = client or TrilithClient()

    @tool
    def trilith_write(
        id: str,
        content: str,
        tier: str = "SEMANTIC",
        scope: str = "USER",
    ) -> str:
        """Store a durable fact or event in Trilith memory."""
        return json.dumps(c.write(id=id, content=content, tier=tier, scope=scope))

    @tool
    def trilith_assemble(
        task: str,
        budget: int = 300,
        requester_scope: str = "USER",
    ) -> str:
        """Fetch budgeted, ranked context for a task before calling the LLM."""
        return json.dumps(c.assemble(task, budget=budget, requester_scope=requester_scope))

    @tool
    def trilith_forget(scope: str) -> str:
        """Physically purge all Trilith memory for a scope."""
        return json.dumps(c.forget(scope))

    return [trilith_write, trilith_assemble, trilith_forget]


def make_assemble_node(
    client: TrilithClient | None = None,
    input_key: str = "input",
    budget: int = 400,
    requester_scope: str = "USER",
) -> Callable[[dict], dict]:
    """LangGraph node: state[input_key] → trilith_memory + trilith_context."""
    c = client or TrilithClient()

    def assemble_node(state: dict) -> dict:
        task = state.get(input_key) or ""
        if not task and state.get("messages"):
            last = state["messages"][-1]
            task = getattr(last, "content", None) or str(last)
        ctx = c.assemble(str(task), budget=budget, requester_scope=requester_scope)
        memory = "\n".join(f"- {i.get('content', '')}" for i in (ctx.get("items") or []))
        return {
            **state,
            "trilith_context": ctx,
            "trilith_memory": memory,
        }

    return assemble_node
