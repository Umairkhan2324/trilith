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

Optional: `pip install -e ".[mcp]"` for the MCP adapter.

---

## 2. In-process Python (recommended for prototypes)

This is the fastest path: embed Trilith in your agent process. No server required.

### Imports and setup

```python
from google.protobuf.timestamp_pb2 import Timestamp

from core.runtime import build_runtime
from core.proto.trilith_pb2 import ContextItem, Tier, Scope

# One shared runtime (SQLite file persists across restarts)
rt = build_runtime("trilith.db")
# Or: build_runtime(":memory:") for ephemeral demos
```

### Write a fact (Semantic tier)

```python
def remember(item_id: str, content: str, scope=Scope.USER) -> None:
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
    rt.semantic.write(item)

remember("pref-lang", "Alice prefers Python for backend work.")
remember("proj", "Alice is building a distributed tracing tool.")
```

### Assemble context (before the LLM call)

```python
assembled = rt.governor.assemble(
    task="What should I know about Alice's work?",
    budget=300,                 # soft token budget (~4 chars ≈ 1 token)
    requester_scope="USER",     # privacy filter uses this
)

for item in assembled.items:
    print(item.id, item.content)

for ex in assembled.excluded_items:
    print("excluded:", ex.item.id, "→", ex.reason)
```

### Inject into your prompt (the integration point)

```python
def build_prompt(user_message: str, budget: int = 400) -> str:
    ctx = rt.governor.assemble(
        task=user_message,
        budget=budget,
        requester_scope="USER",
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
- Auth / multi-tenant IAM (not built yet — local/beta only)

---

## 4. Procedural + Episodic (when you need them)

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
rt.procedural.write(step, subtask_id="deploy-42")
summary = rt.procedural.fold("deploy-42")  # replaces steps with one item

# Episodic: scoped events (scope REQUIRED on query)
event = ContextItem(
    id="evt-1",
    tier=Tier.EPISODIC,
    scope=Scope.TENANT,
    content="User opened billing settings",
    provenance="ui",
)
event.created_at.CopyFrom(ts)
rt.episodic.write(event)

# Purge a scope across ALL tiers (physical delete)
rt.episodic.forget("USER", notify_stores=[rt.semantic, rt.procedural])
```

---

## 5. REST server (multi-language / sidecar)

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

## 6. gRPC (same ops, typed)

```python
import grpc
from google.protobuf.timestamp_pb2 import Timestamp

from core.proto import trilith_pb2, trilith_pb2_grpc
from core.proto.trilith_pb2 import ContextItem, Tier, Scope

channel = grpc.insecure_channel("127.0.0.1:50051")
stub = trilith_pb2_grpc.ContextManagerStub(channel)

ts = Timestamp(); ts.GetCurrentTime()
stub.Write(trilith_pb2.WriteRequest(item=ContextItem(
    id="g1", tier=Tier.SEMANTIC, scope=Scope.USER,
    content="Alice uses Go and Python",
    created_at=ts, provenance="grpc_client",
)))

assembled = stub.Assemble(trilith_pb2.AssembleRequest(
    task_description="What languages does Alice use?",
    budget_tokens=200,
    requester_scope="USER",
))
print([i.content for i in assembled.items])
```

---

## 7. MCP adapter

```bash
pip install -e ".[mcp]"
python adapters/mcp/server.py
```

Tools: `write_context`, `assemble_context`, `forget_scope`.  
Persistence demo: [`examples/mcp_chat.py`](../examples/mcp_chat.py)

---

## Next

- Design deep-dive: [architecture.md](architecture.md)
- Proto contract: [`proto/trilith.proto`](../proto/trilith.proto)
