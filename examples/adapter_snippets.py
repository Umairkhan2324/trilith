"""
Plug-and-play snippets (run against `trilith serve`).

  pip install -e ".[server,langchain,openai-agents]"
  trilith serve
  python examples/adapter_snippets.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.client import TrilithClient


def demo_client() -> None:
    c = TrilithClient()
    c.write("demo-1", "Alice prefers TypeScript for frontend work.")
    print("assemble:", c.assemble("What does Alice prefer?", budget=200))
    print("memory:\n", c.memory_block("What does Alice prefer?"))


def demo_langchain_import() -> None:
    try:
        from adapters.langchain import make_assemble_node, make_trilith_tools
    except ImportError as exc:
        print("langchain skipped:", exc)
        return
    tools = make_trilith_tools()
    node = make_assemble_node()
    print("langchain tools:", [t.name for t in tools])
    print("langgraph node keys:", list(node({"input": "Alice prefs"}).keys()))


def demo_openai_agents_import() -> None:
    try:
        from adapters.openai_agents import make_trilith_tools
    except ImportError as exc:
        print("openai-agents skipped:", exc)
        return
    tools = make_trilith_tools()
    print("openai-agents tools:", [t.name for t in tools])


def demo_claude_schemas() -> None:
    from adapters.claude_sdk import TRILITH_TOOL_SCHEMAS, run_trilith_tool

    print("claude tools:", [t["name"] for t in TRILITH_TOOL_SCHEMAS])
    print(run_trilith_tool("trilith_assemble", {"task": "Alice prefs", "budget": 200}))


if __name__ == "__main__":
    print("=== shared client ===")
    try:
        demo_client()
    except Exception as exc:
        print("Start server first: trilith serve\n", exc)
        sys.exit(0)
    print("\n=== langchain ===")
    demo_langchain_import()
    print("\n=== openai agents ===")
    demo_openai_agents_import()
    print("\n=== claude ===")
    demo_claude_schemas()
