"""In-process Trilith usage: write → assemble → prompt.

Run from repo root:
    python examples/in_process_usage.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.ops import write_item
from core.proto.trilith_pb2 import ContextItem, Scope, Tier
from core.runtime import build_runtime

DB = ":memory:"  # use "trilith.db" for persistence across restarts

# One user, one workspace: the default tenant with no owner named.
# See examples/multi_tenant_usage.py for the many-customers version.
ME = Principal()


def remember(rt, item_id: str, content: str) -> None:
    ts = Timestamp()
    ts.GetCurrentTime()
    write_item(
        rt,
        ContextItem(
            id=item_id,
            tier=Tier.SEMANTIC,
            # TENANT = visible to everyone in this workspace. Use Scope.USER
            # with an owner_id when an item must stay private to one person.
            scope=Scope.TENANT,
            content=content,
            provenance="in_process_example",
            created_at=ts,
        ),
        principal=ME,
    )


def build_prompt(rt, user_message: str, budget: int = 400) -> tuple[str, object]:
    ctx = rt.governor.assemble(
        task=user_message,
        budget=budget,
        principal=ME,
    )
    memory = "\n".join(f"- {i.content}" for i in ctx.items)
    prompt = (
        "You are a helpful assistant.\n"
        f"Known context (budgeted):\n{memory}\n\n"
        f"User: {user_message}"
    )
    return prompt, ctx


def main() -> None:
    rt = build_runtime(DB)
    remember(rt, "pref", "Alice prefers Python for backend work.")
    remember(rt, "proj", "Alice is building a distributed tracing tool.")

    user = "What is Alice working on?"
    prompt, ctx = build_prompt(rt, user)
    print("=== Assembled items ===")
    for item in ctx.items:
        print(f"  [{item.id}] {item.content}")
    print(f"\ntokens_used={ctx.tokens_used}")
    print("\n=== Prompt you would send to an LLM ===\n")
    print(prompt)


if __name__ == "__main__":
    main()
