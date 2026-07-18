"""
Trilith MCP Chat Example
========================
Demonstrates persistent memory across sessions using the Trilith
Semantic store. This script simulates two "turns" of a conversation:

  Turn 1 — The agent learns facts about the user and writes them
            to the SEMANTIC tier.

  Turn 2 — On a fresh Governor instance (simulating a restart), the
            agent calls assemble() and retrieves those facts,
            proving persistence.

Run from the repo root:
    python examples/mcp_chat.py
"""

import os
import sys

# Make sure the repo root is on the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.protobuf.timestamp_pb2 import Timestamp

from core.proto.trilith_pb2 import ContextItem, Tier, Scope
from core.sqlite_backend import SQLiteBackend
from core.semantic import SemanticStore
from core.procedural import ProceduralStore
from core.episodic import EpisodicStore
from core.privacy import PolicyEngine
from core.governor import Governor

DB_PATH = "example_chat.db"  # persistent file-based SQLite

# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def make_item(item_id: str, content: str, scope: Scope = Scope.USER) -> ContextItem:
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


def build_governor(db_path: str) -> Governor:
    """Construct a fresh Governor backed by a persistent SQLite file."""
    backend = SQLiteBackend(db_path)
    sem = SemanticStore(backend)
    proc = ProceduralStore(backend)
    epi = EpisodicStore(backend)
    policy = PolicyEngine()
    return Governor(
        semantic_store=sem,
        procedural_store=proc,
        episodic_store=epi,
        policy_engine=policy,
    )


# ──────────────────────────────────────────────────────────
# Turn 1 — Agent learns and stores facts
# ──────────────────────────────────────────────────────────

def turn_1():
    print("=" * 60)
    print("TURN 1 — Writing user facts to Semantic tier")
    print("=" * 60)

    gov = build_governor(DB_PATH)

    facts = [
        ("fact-name",  "The user's name is Alice."),
        ("fact-lang",  "Alice prefers Python as her primary language."),
        ("fact-proj",  "Alice is currently working on a distributed tracing tool."),
        ("fact-skill", "Alice has 7 years of backend engineering experience."),
    ]

    for item_id, content in facts:
        item = make_item(item_id, content)
        gov.semantic_store.write(item)
        print(f"  [WROTE] {item_id}: {content}")

    print()


# ──────────────────────────────────────────────────────────
# Turn 2 — Fresh Governor retrieves facts via assemble()
# ──────────────────────────────────────────────────────────

def turn_2():
    print("=" * 60)
    print("TURN 2 — Fresh Governor, assemble() retrieves persisted facts")
    print("=" * 60)

    # Simulate a restart by building a brand-new Governor instance
    gov = build_governor(DB_PATH)

    task = "What do I know about the user?"
    assembled = gov.assemble(task=task, budget=300, requester_scope="USER")

    print(f"\nTask   : {task}")
    print(f"Budget : 300 tokens  |  Used: {assembled.tokens_used} tokens")
    print(f"\nAssembled {len(assembled.items)} item(s):\n")
    for item in assembled.items:
        print(f"  • [{item.id}] {item.content}")

    if assembled.excluded_items:
        print(f"\nExcluded {len(assembled.excluded_items)} item(s):")
        for ex in assembled.excluded_items:
            print(f"  ✗ [{ex.item.id}] — {ex.reason}")

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
