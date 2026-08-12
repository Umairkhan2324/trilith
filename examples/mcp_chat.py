"""
Trilith MCP Chat Example
========================
Demonstrates persistent memory across sessions using the Trilith
Semantic store. This script simulates two "turns" of a conversation:

  Turn 1 — The agent learns facts about the user and writes them
            to the SEMANTIC tier.

  Turn 2 — On a fresh runtime (simulating a restart), the agent calls
            assemble() and retrieves those facts, proving persistence.

Run from the repo root:
    python examples/mcp_chat.py
"""

import os
import sys

# Make sure the repo root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.protobuf.timestamp_pb2 import Timestamp  # noqa: E402

from core.identity import Principal  # noqa: E402
from core.ops import write_item  # noqa: E402
from core.proto.trilith_pb2 import ContextItem, Scope, Tier  # noqa: E402
from core.runtime import build_runtime  # noqa: E402

DB_PATH = "example_chat.db"  # persistent file-based SQLite

# The workspace this demo writes into. Change tenant_id to keep several
# customers' memory apart inside the same database file.
ME = Principal(tenant_id="default")


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def make_item(item_id: str, content: str, scope: Scope = Scope.TENANT) -> ContextItem:
    ts = Timestamp()
    ts.GetCurrentTime()
    return ContextItem(
        id=item_id,
        tier=Tier.SEMANTIC,
        scope=scope,
        content=content,
        provenance="mcp_chat_example",
        created_at=ts,
    )


# ──────────────────────────────────────────────────────────
# Turn 1 — Agent learns and stores facts
# ──────────────────────────────────────────────────────────

def turn_1():
    print("=" * 60)
    print("TURN 1 - Writing user facts to Semantic tier")
    print("=" * 60)

    rt = build_runtime(DB_PATH)

    facts = [
        ("fact-name",  "The user's name is Alice."),
        ("fact-lang",  "Alice prefers Python as her primary language."),
        ("fact-proj",  "Alice is currently working on a distributed tracing tool."),
        ("fact-skill", "Alice has 7 years of backend engineering experience."),
    ]

    for item_id, content in facts:
        write_item(rt, make_item(item_id, content), principal=ME)
        print(f"  [WROTE] {item_id}: {content}")

    print()


# ──────────────────────────────────────────────────────────
# Turn 2 — Fresh runtime retrieves facts via assemble()
# ──────────────────────────────────────────────────────────

def turn_2():
    print("=" * 60)
    print("TURN 2 - Fresh runtime, assemble() retrieves persisted facts")
    print("=" * 60)

    # Simulate a restart by building a brand-new runtime instance
    rt = build_runtime(DB_PATH)

    task = "What do I know about the user?"
    assembled = rt.governor.assemble(task=task, budget=300, principal=ME)

    print(f"\nTask   : {task}")
    print(f"Budget : 300 tokens  |  Used: {assembled.tokens_used} tokens")
    print(f"\nAssembled {len(assembled.items)} item(s):\n")
    for item in assembled.items:
        print(f"  + [{item.id}] {item.content}")

    if assembled.excluded_items:
        print(f"\nExcluded {len(assembled.excluded_items)} item(s):")
        for ex in assembled.excluded_items:
            print(f"  x [{ex.item.id}] - {ex.reason}")

    print()


# ──────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Clean up any previous run's DB so the demo is reproducible
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"(Removed previous DB: {DB_PATH})\n")

    turn_1()
    turn_2()

    # Clean up after demo
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
