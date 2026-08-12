# Trilith Quickstart

From install → import → call → inject into an LLM prompt.  
Trilith does **not** call an LLM; you do. It decides **which memory** enters the prompt under a token budget.

---

## 1. Install

```bash
git clone https://github.com/Umairkhan2324/trilith.git
cd trilith
pip install -e ".[server]"
```

Optional: `pip install -e ".[mcp]"` for MCP, or `pip install -e ".[adapters]"` for LangChain + OpenAI Agents + Claude extras.

> **Using LangGraph / OpenAI Agents / Claude / TypeScript?**  
> Skip the in-process core and use **[adapters.md](adapters.md)** — start `trilith serve`, then import the drop-in tools/client.

---

## 2. In-process Python (recommended for prototypes)

This is the fastest path: embed Trilith in your agent process. No server required.

### Imports and setup

```python
from google.protobuf.timestamp_pb2 import Timestamp

from core.identity import Principal
from core.ops import write_item
from core.runtime import build_runtime
from core.proto.trilith_pb2 import ContextItem, Tier, Scope

# One shared runtime (SQLite file persists across restarts)
rt = build_runtime("trilith.db")
# Or: build_runtime(":memory:") for ephemeral demos

# Who this process is acting as. A bare Principal() is the default tenant
# with no user named — right for a single-workspace app.
ME = Principal()
```

### Write a fact (Semantic tier)

```python
def remember(item_id: str, content: str, scope=Scope.TENANT) -> None:
    ts = Timestamp()
    ts.GetCurrentTime()
    item = ContextItem(
        id=item_id,
        tier=Tier.SEMANTIC,
        scope=scope,
        content=content,
        provenance="my_agent",
        created_at=ts,
    )
    write_item(rt, item, principal=ME)   # stamps tenant/owner from the principal

remember("pref-lang", "Alice prefers Python for backend work.")
remember("proj", "Alice is building a distributed tracing tool.")
```

> **Why `Scope.TENANT`?** It means *visible to everyone in this workspace* — the right
> default for a single-user app. `Scope.USER` means *private to one named person*, so it
> only isolates anything if you also pass an `owner_id`. Trilith won't hand a `USER` item
> to an anonymous reader and pretend that was isolation.

### Assemble context (before the LLM call)

```python
assembled = rt.governor.assemble(
    task="What should I know about Alice's work?",
    budget=300,          # soft token budget (~4 chars ≈ 1 token)
    principal=ME,        # tenant/user/session identity drives the privacy filter
)

for item in assembled.items:
    print(item.id, item.content)

for ex in assembled.excluded_items:
    print("excluded:", ex.item.id, "→", ex.reason)

if assembled.candidates_truncated:
    print(f"note: {assembled.candidates_truncated} candidates never reached ranking")
```

> Upgrading from v0.1? `assemble(task, budget, requester_scope="USER")` still works
> exactly as before. See [deployment.md](deployment.md#migrating-a-v01-database).

### Inject into your prompt (the integration point)

```python
def build_prompt(user_message: str, budget: int = 400) -> str:
    ctx = rt.governor.assemble(
        task=user_message,
        budget=budget,
        principal=ME,
    )
    memory_block = "\n".join(f"- {i.content}" for i in ctx.items)
    return (
        "You are a helpful assistant.\n"
        f"Known context (budgeted):\n{memory_block}\n\n"
        f"User: {user_message}"
    )

prompt = build_prompt("What is Alice working on?")
# → pass `prompt` to OpenAI / Anthropic / local model (your code)
```

Runnable demo: [`examples/in_process_usage.py`](../examples/in_process_usage.py)

```bash
python examples/in_process_usage.py
```

---

## 3. Where to use it optimally

Put Trilith **in the agent loop**, not inside the model:

```text
user message
    │
    ├─① optional: write durable facts you just learned  →  rt.semantic.write(...)
    │
    ├─② ALWAYS: assemble(task=user_message, budget=N)   →  memory block
    │
    ├─③ build prompt = system + memory + user
    │
    └─④ call your LLM with that prompt
```

### Good fit

| Situation | Why Trilith |
|-----------|-------------|
| Chatbots with long-term user prefs | Semantic write once, assemble every turn |
| Agents that must respect token caps | `budget` + exclusion audit |
| Multi-tool agents drowning in history | Rank + distraction penalty vs dumping logs |
| MCP hosts (Claude Desktop, Cursor) | Use MCP tools instead of custom memory |
| Session cleanup / “forget me” | `forget(scope)` physical delete |

### Minimal agent turn (pattern)

```python
def handle_turn(user_text: str, learn: str | None = None) -> str:
    # ① Learn (only when you have a durable fact)
    if learn:
        remember(f"fact-{hash(learn) % 10_000}", learn)

    # ② Assemble → ③ Prompt → ④ Your LLM
    prompt = build_prompt(user_text, budget=500)
    # return call_llm(prompt)   # plug in your provider
    return prompt  # demo: return the prompt itself
```

### Poor fit (don’t force it)

- One-shot scripts with no memory
- Replacing your vector DB / RAG corpus wholesale (Trilith governs *working* context; RAG can feed it later)
- End-user identity management — Trilith isolates by `tenant_id`/`owner_id`, but it is not
  an IAM system. Your app authenticates its users and tells Trilith who they are.

---

## 4. Many users and customers

Isolation has two layers. `tenant_id` is a hard wall between customers; `owner_id` and
`session_id` narrow visibility *inside* one customer.

```python
acme   = Principal(tenant_id="acme")                            # the whole tenant
alice  = Principal(tenant_id="acme", owner_id="alice")          # one user
chat   = Principal(tenant_id="acme", owner_id="alice", session_id="s1")
globex = Principal(tenant_id="globex")                          # another customer

def remember_for(principal, item_id, content, scope=Scope.TENANT):
    ts = Timestamp()
    ts.GetCurrentTime()
    write_item(rt, ContextItem(
        id=item_id, tier=Tier.SEMANTIC, scope=scope,
        content=content, provenance="app", created_at=ts,
    ), principal=principal)

remember_for(acme,  "plan", "Acme is migrating billing to Stripe.", Scope.TENANT)
remember_for(alice, "pref", "Alice prefers Python.",                Scope.USER)

rt.governor.assemble("billing", 300, principal=alice)   # sees both
rt.governor.assemble("billing", 300, principal=acme)    # sees only the tenant plan
rt.governor.assemble("billing", 300, principal=globex)  # sees neither
```

Cross-tenant rows are filtered in SQL, so globex's data is never ranked, never budgeted,
and never listed as excluded. Runnable demo:
[`examples/multi_tenant_usage.py`](../examples/multi_tenant_usage.py).

Serving this over HTTP? Mint one API key per tenant so callers can't choose their own —
see **[deployment.md](deployment.md)**.

---

## 5. Procedural + Episodic (when you need them)

```python
# Procedural: steps of a task, then fold into one summary
step = ContextItem(
    id="step-1",
    tier=Tier.PROCEDURAL,
    scope=Scope.SESSION,
    content="Cloned repo and installed deps",
    provenance="planner",
)
ts = Timestamp(); ts.GetCurrentTime(); step.created_at.CopyFrom(ts)
ME.stamp(step)                       # apply tenant/owner/session
rt.procedural.write(step, subtask_id="deploy-42")

# Collapse the steps into one item once the sub-task is done, so they stop
# consuming budget on every later assemble.
summary = rt.procedural.fold("deploy-42", principal=ME)

# Episodic: scoped events. Never cross a tenant boundary, not even GLOBAL ones.
event = ContextItem(
    id="evt-1",
    tier=Tier.EPISODIC,
    scope=Scope.TENANT,
    content="User opened billing settings",
    provenance="ui",
)
event.created_at.CopyFrom(ts)
write_item(rt, event, principal=ME)

# Purge a scope across ALL tiers (physical delete), confined to this principal's
# tenant — and to their own owner_id when the scope is USER.
from core.ops import forget_scope, purge_expired
forget_scope(rt, "USER", principal=ME)

# Reap items past their TTL (also runs automatically at startup).
purge_expired(rt, principal=ME)
```

---

## 6. REST server (multi-language / sidecar)

```bash
trilith serve --host 127.0.0.1 --port 8080 --grpc-port 50051
```

| Surface | Address |
|---------|---------|
| REST | `http://127.0.0.1:8080` |
| gRPC | `127.0.0.1:50051` |

```bash
# Write
curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f1","tier":"SEMANTIC","scope":"USER","content":"Alice prefers Python."}'

# Assemble (use this output in your prompt builder)
curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Content-Type: application/json" \
  -d '{"task":"What does Alice prefer?","budget":200,"requester_scope":"USER"}'

# Forget
curl -s -X POST http://127.0.0.1:8080/v1/forget \
  -H "Content-Type: application/json" \
  -d '{"scope":"USER"}'
```

Python against REST:

```python
import requests

BASE = "http://127.0.0.1:8080"

requests.post(f"{BASE}/v1/write", json={
    "id": "f1", "tier": "SEMANTIC", "scope": "USER",
    "content": "Alice prefers Python.",
})

ctx = requests.post(f"{BASE}/v1/assemble", json={
    "task": "What does Alice prefer?",
    "budget": 200,
    "requester_scope": "USER",
}).json()

memory = "\n".join(i["content"] for i in ctx["items"])
prompt = f"Context:\n{memory}\n\nUser: What does Alice prefer?"
```

---

## 7. gRPC (same ops, typed)

```python
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from core.proto import trilith_pb2, trilith_pb2_grpc
from core.proto.trilith_pb2 import ContextItem, Tier, Scope

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = trilith_pb2_grpc.ContextManagerStub(channel)

ts = Timestamp(); ts.GetCurrentTime()
acme = trilith_pb2.Principal(tenant_id="acme", owner_id="alice")

stub.Write(trilith_pb2.WriteRequest(
    item=ContextItem(
        id="g1", tier=Tier.SEMANTIC, scope=Scope.TENANT,
        content="Alice uses Go and Python",
        created_at=ts, provenance="grpc_client",
    ),
    principal=acme,
))

assembled = stub.Assemble(trilith_pb2.AssembleRequest(
    task_description="What languages does Alice use?",
    budget_tokens=200,
    principal=acme,
))
print([i.content for i in assembled.items])

# Also available: Query, Forget, Fold, PurgeExpired.
# With auth on, pass metadata=(("authorization", f"Bearer {key}"),) on every call.
```

---

## 8. MCP adapter

```bash
pip install -e ".[mcp]"
python adapters/mcp/server.py
```

Tools: `write_context`, `assemble_context`, `fold_procedural`, `forget`,
`purge_expired_items`. Each takes a `tenant_id` (default `"default"`), so one MCP
host can serve several isolated workspaces from one database file.  
Persistence demo: [`examples/mcp_chat.py`](../examples/mcp_chat.py)

---

## Next

- Tenants, API keys, Docker, migrating a v0.1 database: [deployment.md](deployment.md)
- Design deep-dive: [architecture.md](architecture.md)
- Proto contract: [`proto/trilith.proto`](../proto/trilith.proto)
