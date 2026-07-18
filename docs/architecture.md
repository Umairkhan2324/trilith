# Trilith Architecture

Trilith is a language-agnostic context management layer that sits between AI agents and their memory. It answers the question: *"What context should this agent see right now, given limited token budget, multiple memory tiers, privacy constraints, and the risk of distraction?"*

---

## Core Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Auditable by default** | Every `assemble` call returns both included *and* excluded items with explicit reasons |
| **Privacy-first** | The Policy Engine runs *before* the Governor ranks anything — data you can't see is never scored |
| **Pluggable backends** | Each tier uses a backend interface; swap in a vector DB without changing the Governor |
| **Language-agnostic** | Protobuf schema + dual gRPC/REST gateway makes every operation callable from any language |
| **Zero external API dependency** | Default scorer is pure TF-IDF (no OpenAI, no Cohere) |

---

## Three-Tier Memory Model

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent / Client                          │
└────────────────────────┬────────────────────────────────────┘
                         │  assemble(task, budget, scope)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Governor                              │
│  1. Query all three tiers                                   │
│  2. Run PolicyEngine.filter() — scope check, expiry, PII   │
│  3. Rank via TF-IDF + distraction penalty                   │
│  4. Fill budget greedily, log excluded items + reasons      │
└───────────────┬───────────────────┬────────────────┬────────┘
                │                   │                │
      ┌─────────▼────────┐  ┌───────▼──────┐  ┌────▼────────┐
      │  SEMANTIC Store   │  │  PROCEDURAL  │  │  EPISODIC   │
      │  Long-term facts  │  │  Task steps  │  │  Events     │
      │  Pluggable index  │  │  + fold()    │  │  Scoped     │
      │  (SQLite default) │  │              │  │  + forget() │
      └───────────────────┘  └──────────────┘  └─────────────┘
```

### Semantic Tier (`core/semantic.py`)
Stores durable world-knowledge and facts. Backed by SQLite by default; the interface is designed so a vector-DB adapter (Chroma, Qdrant, Pinecone) can be swapped in without touching the Governor.

### Procedural Tier (`core/procedural.py`)
Stores steps and sub-task records. Adds a `fold(subtask_id)` operation that collapses a sequence of steps into a single summary item, preventing unbounded context growth on long tasks.

### Episodic Tier (`core/episodic.py`)
Stores session or tenant-scoped events. Two hard rules:
- **Every read requires a scope** — no accidental cross-tenant access, even by omission.
- **`forget(scope)`** physically deletes from this store *and* cascades deletes with the same scope to the Semantic and Procedural stores.

---

## Governor (`core/governor.py`)

### Ranking
Default scorer is **TF-IDF cosine similarity** (no external dependencies). A pluggable `Scorer` interface means you can inject any embedding model.

### Distraction Penalty
Items that score high pairwise similarity to the *rest of the corpus* but low similarity to the *query* are penalised. The formula used:

```
final_score = task_similarity − (distraction_coef × max(0, corpus_similarity − task_similarity))
```

This prevents "generic" documents that happen to share keywords with everything from crowding out the specific, task-relevant ones.

### Assembly (`assemble`)
```
assemble(task, budget, requester_scope)
  → AssembledContext { items[], tokens_used, excluded_items[{item, reason}] }
```
Token budget is enforced strictly (≤ budget, never over). Every excluded item is logged with a human-readable reason string.

---

## Privacy Engine (`core/privacy.py`)

Runs *before* ranking. Three checks in order:

1. **Expiry** — drops items past `expires_at`
2. **Scope matching** — GLOBAL items visible to all; all others must match `requester_scope`
3. **PII Redaction** — regex-based in-place redaction of emails, phone numbers, and national ID formats before handing content to the Governor

---

## Language-Agnostic Interface

```
          ┌────────────────────────────────────────────┐
          │           Any Client Language              │
          │   Python · TypeScript · Go · Rust · curl  │
          └───────────┬─────────────────┬──────────────┘
                      │                 │
               gRPC (50051)      REST/JSON (8080)
                      │                 │
          ┌───────────▼─────────────────▼──────────────┐
          │           Trilith Server (trilith serve)    │
          │       FastAPI + gRPC servicer               │
          └────────────────────┬───────────────────────┘
                               │
                          Governor + Tiers
```

- **`proto/trilith.proto`** is the single source of truth for types and operations. Any language with `protoc` support can compile native bindings.
- **REST gateway** (`/v1/write`, `/v1/assemble`, `/v1/forget`) accepts standard JSON — usable with `curl`, `fetch`, `requests`, or any HTTP client.
- **MCP adapter** (`adapters/mcp/server.py`) exposes the same operations as Model Context Protocol tools, compatible with Claude Desktop, Cursor, and any other MCP host.
- **SDK stubs** in `sdks/python`, `sdks/typescript`, `sdks/go` wrap the HTTP/gRPC client boilerplate into idiomatic native APIs.

---

## Repository Layout

```
trilith/
├── proto/                  # Protobuf schema (source of truth)
│   └── trilith.proto
├── core/                   # Python reference implementation
│   ├── proto/              # Generated gRPC/protobuf bindings
│   │   ├── trilith_pb2.py
│   │   └── trilith_pb2_grpc.py
│   ├── sqlite_backend.py   # Pluggable storage backend
│   ├── semantic.py         # Semantic tier
│   ├── procedural.py       # Procedural tier + fold()
│   ├── episodic.py         # Episodic tier + forget() cascade
│   ├── governor.py         # Ranking, distraction penalty, assemble
│   ├── privacy.py          # PolicyEngine (scope, PII, expiry)
│   └── cli.py              # `trilith serve` entrypoint
├── adapters/
│   └── mcp/                # MCP server adapter
│       └── server.py
├── sdks/                   # Language SDK stubs
│   ├── python/
│   ├── typescript/
│   └── go/
├── examples/
│   └── mcp_chat.py         # Two-turn persistent memory demo
├── tests/                  # Pytest test suites
├── docs/
│   ├── quickstart.md
│   └── architecture.md
├── pyproject.toml          # pip-installable package (trilith-core)
├── Dockerfile              # Zero-config container
└── .github/workflows/ci.yml
```
