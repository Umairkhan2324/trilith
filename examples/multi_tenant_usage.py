"""Multi-tenant Trilith: two customers, several users, one database.

Run from repo root:
    python examples/multi_tenant_usage.py

Shows the two layers of isolation:
  * tenant_id  — a hard boundary; acme never sees globex, ever
  * scope      — narrows visibility *within* a tenant (TENANT / USER / SESSION)

and that GLOBAL is the one deliberate exception that crosses tenants.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from google.protobuf.timestamp_pb2 import Timestamp  # noqa: E402

from core.identity import Principal  # noqa: E402
from core.ops import forget_scope, write_item  # noqa: E402
from core.proto.trilith_pb2 import ContextItem, Scope, Tier  # noqa: E402
from core.runtime import build_runtime  # noqa: E402

DB = ":memory:"  # use a file path to persist across restarts


def remember(rt, principal, item_id, content, scope=Scope.TENANT, tier=Tier.SEMANTIC):
    ts = Timestamp()
    ts.GetCurrentTime()
    item = ContextItem(
        id=item_id,
        tier=tier,
        scope=scope,
        content=content,
        provenance="multi_tenant_example",
        created_at=ts,
    )
    write_item(rt, item, principal=principal)


def show(rt, label, principal, task, budget=400):
    ctx = rt.governor.assemble(task=task, budget=budget, principal=principal)
    print(f"\n--- {label} ({principal.describe()}) ---")
    print(f"  task: {task!r}   tokens_used={ctx.tokens_used}")
    if ctx.items:
        for item in ctx.items:
            print(f"  [+] {item.id}: {item.content}")
    else:
        print("  [+] (nothing visible)")
    for ex in ctx.excluded_items:
        print(f"  [-] {ex.item.id}: {ex.reason}")


def main() -> None:
    rt = build_runtime(DB)

    # Two customers. Inside acme, two users and one live session.
    acme = Principal(tenant_id="acme")
    alice = Principal(tenant_id="acme", owner_id="alice")
    bob = Principal(tenant_id="acme", owner_id="bob")
    alice_session = Principal(tenant_id="acme", owner_id="alice", session_id="sess-1")
    globex = Principal(tenant_id="globex")

    # Tenant-wide knowledge: everyone at acme sees this.
    remember(rt, acme, "acme-plan", "Acme is migrating billing to Stripe.")
    # Per-user: only alice sees hers, only bob sees his.
    remember(rt, alice, "alice-pref", "Alice prefers Python for billing work.", Scope.USER)
    remember(rt, bob, "bob-pref", "Bob prefers Go for billing work.", Scope.USER)
    # Per-session episodic event.
    remember(
        rt, alice_session, "sess-evt",
        "Alice opened the billing migration checklist.",
        Scope.SESSION, Tier.EPISODIC,
    )
    # The other customer's data.
    remember(rt, globex, "globex-plan", "Globex is migrating billing to Adyen.")
    # Cross-tenant system knowledge.
    remember(rt, acme, "policy", "Never expose raw billing credentials.", Scope.GLOBAL)

    task = "What is happening with billing?"

    show(rt, "Acme, no user named", acme, task)
    show(rt, "Acme / Alice", alice, task)
    show(rt, "Acme / Alice in session", alice_session, task)
    show(rt, "Acme / Bob", bob, task)
    show(rt, "Globex", globex, task)

    # "Forget me" for one user does not touch anyone else.
    print("\n=== alice asks to be forgotten ===")
    deleted = forget_scope(rt, "USER", principal=alice)
    print(f"  {deleted} episodic item(s) purged; USER-scoped semantic and")
    print("  procedural items owned by alice were cascaded too (see below).")
    show(rt, "Acme / Alice after forget", alice, task)
    show(rt, "Acme / Bob after forget", bob, task)

    print("\nNote: globex never appeared in an acme result -- not even as an")
    print("excluded item. Cross-tenant rows are filtered in SQL, so they are")
    print("never ranked, never audited, and never counted against a budget.")


if __name__ == "__main__":
    main()
