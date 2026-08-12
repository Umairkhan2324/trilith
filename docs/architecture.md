# Trilith Architecture

Trilith is a language-agnostic context management layer that sits between AI agents and their memory. It answers the question: *"What context should this agent see right now, given limited token budget, multiple memory tiers, privacy constraints, and the risk of distraction?"*

---

## Core Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Auditable by default** | Every `assemble` call returns both included *and* excluded items with explicit reasons |
| **Isolation before everything** | `tenant_id` is filtered in SQL — another tenant's row is never fetched, never ranked, never audited |
| **Privacy-first** | The Policy Engine runs *before* the Governor ranks anything — data you can't see is never scored |
| **Pluggable backends** | Each tier uses a backend interface; swap in a vector DB without changing the Governor |
| **Language-agnostic** | Protobuf schema + dual gRPC/REST gateway makes every operation callable from any language |
| **Zero external API dependency** | Default scorer is pure TF-IDF (no OpenAI, no Cohere) |
| **Secure by escalation, not by default** | Auth is off for local work and one command away; once on, it cannot be switched back off by revoking keys |

---

## Three-Tier Memory Model

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent / Client                          │
└────────────────────────┬────────────────────────────────────┘
                         │  assemble(task, budget, principal)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              AuthEnforcer  →  Principal                     │
│  API key (or open mode) → tenant_id / owner_id / session_id │
└────────────────────────┬────────────────────────────────────┘
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                       Governor                              │
│  1. Query all three tiers, scoped to the principal's tenant │
│     and capped at max_candidates (newest first)             │
│  2. Run PolicyEngine.filter() — expiry, tenant, scope, PII  │
│  3. Rank via TF-IDF + distraction penalty                   │
│  4. Fill budget greedily, log excluded items + reasons      │
└───────────────┬───────────────────┬────────────────┬────────┘
                │                   │                │
      ┌─────────▼────────┐  ┌───────▼──────┐  ┌────▼────────┐
      │  SEMANTIC Store   │  │  PROCEDURAL  │  │  EPISODIC   │
      │  Long-term facts  │  │  Task steps  │  │  Events     │
      │  Pluggable index  │  │  + fold()    │  │  Tenant-    │
      │  (SQLite default) │  │              │  │  bound      │
      │                   │  │              │  │  + forget() │
      └───────────────────┘  └──────────────┘  └─────────────┘
```

### Semantic Tier (`core/semantic.py`)
Stores durable world-knowledge and facts. Backed by SQLite by default; the interface is designed so a vector-DB adapter (Chroma, Qdrant, Pinecone) can be swapped in without touching the Governor.

### Procedural Tier (`core/procedural.py`)
Stores steps and sub-task records. Adds a `fold(subtask_id)` operation that collapses a sequence of steps into a single summary item, preventing unbounded context growth on long tasks.

### Episodic Tier (`core/episodic.py`)
Stores session- or tenant-scoped events. Two hard rules:
- **Events never leave their tenant.** Unlike the other tiers, episodic reads do not
  include `GLOBAL` items — there is no such thing as a cross-tenant event.
- **`forget(scope)`** physically deletes from this store *and* cascades deletes with the
  same scope to the Semantic and Procedural stores — confined to the caller's tenant,
  and further to their own `owner_id`/`session_id` when the scope is `USER` or `SESSION`,
  so "forget me" cannot become "forget everyone".

The v0.1 rule — *every read requires a scope string* — was an approximation of tenant
isolation built before tenants existed. It survives on the legacy `query(scope=...)`
path, but a call carrying a `Principal` is bounded by `tenant_id` instead, which is
both stricter and unable to fail the way the old guard did.

---

## Identity & Isolation (`core/identity.py`, `core/auth.py`)

Two layers, evaluated in order. The first is absolute; the second is a refinement.

### Layer 1 — `tenant_id`

Filtered in the `WHERE` clause. A foreign tenant's row is never loaded, so it cannot be
ranked, cannot consume budget, and does not appear in `excluded_items`. Trilith will not
tell tenant A that tenant B has a document it declined to show. Empty normalises to the
literal tenant `default`; there is no unowned row.

### Layer 2 — `Scope`

Not an identity — a *sharing level* inside the tenant.

| Scope | Visible to | Needs |
|-------|-----------|-------|
| `GLOBAL` | every principal in every tenant | — |
| `TENANT` | every principal of the owning tenant | — |
| `USER` | one user | matching `owner_id` |
| `SESSION` | one session | matching `session_id` |

An item scoped `USER` that carries no `owner_id` **cannot be isolated** — there is no
user to withhold it from — so it degrades to tenant visibility for any identified
caller. This is deliberate: it is what makes migrated v0.1 rows readable instead of
orphaned, and it refuses to imply an isolation guarantee the data cannot support.

### The Principal

```python
Principal(tenant_id="acme", owner_id="alice", session_id="sess-1")
```

In-process you build one directly. Over the wire, `AuthEnforcer.resolve()` builds it:

- **Auth off** — the caller's own values are trusted. This is what makes the local
  quickstart credential-free.
- **Auth on** — the API key supplies `tenant_id` (and `owner_id` if pinned), and any
  client-supplied value for those is **discarded, not merged**. Multi-tenancy is only
  real if the caller cannot pick their own tenant.

### API keys

`tri_<43 url-safe chars>`, stored as a SHA-256 hash and shown exactly once. They live in
an `api_keys` table in the same SQLite file as the context, so one volume is the whole
backup — and a key is scoped to the database it was minted into.

Auth turns on when the first key is minted (no restart) or when `--require-auth` /
`TRILITH_REQUIRE_AUTH=1` is set. It is a **one-way door**: revoking every key leaves auth
on. Otherwise "revoke the last key" would read as locking the door while unlocking it.

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

### Cost, and why it is bounded

The distraction penalty compares every candidate against every other, so assembly is
**O(n²)** in the candidate count. Two guards keep that from becoming a latency cliff on
a large store, and neither is silent:

| Guard | Default | Effect |
|-------|---------|--------|
| `max_candidates` | 500 per tier | Caps rows fetched, newest first. Anything cut is reported in `candidates_truncated`. |
| `max_pairwise` | 400 | Above this, the pairwise matrix is skipped and ranking falls back to task similarity alone. |

A non-zero `candidates_truncated` means your store holds more matching items than one
assembly weighed — the same "no silent drops" contract the exclusion audit provides,
applied to the retrieval step.

### Assembly (`assemble`)
```
assemble(task, budget, principal)          # requester_scope still accepted (v0.1)
  → AssembledContext {
      items[], tokens_used,
      excluded_items[{item, reason}],
      candidates_truncated,
    }
```
Token budget is enforced strictly (≤ budget, never over). Every excluded item is logged
with a human-readable reason string.

---

## Privacy Engine (`core/privacy.py`)

Runs *before* ranking. Four checks, cheapest and most absolute first:

1. **Expiry** — drops items past `expires_at` (and `purge_expired` later reaps them from disk)
2. **Tenant** — the hard boundary; only `Scope.GLOBAL` crosses it
3. **Scope kind** — `TENANT` / `USER` / `SESSION` narrowing inside the tenant
4. **PII Redaction** — regex redaction of emails, phone numbers, and national ID formats,
   applied to a **copy** so stored items are never mutated

Denials carry a specific reason — `Tenant isolation`, `Owner mismatch`,
`Session mismatch`, `Scope mismatch`, `Item expired` — so an empty result is always
explicable. The exception is cross-tenant rows, which are excluded in SQL and therefore
never reach this stage at all.

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
- **REST gateway** on port **8080** — `/v1/write`, `/v1/assemble`, `/v1/forget`, `/v1/fold`,
  `/v1/purge-expired`, `/v1/whoami`, `/healthz`. Usable with `curl`, `fetch`, or any HTTP client.
- **gRPC** (`trilith.ContextManager`) on port **50051** — `Write` / `Query` / `Assemble` /
  `Forget` / `Fold` / `PurgeExpired`; started by `trilith serve` alongside REST.
- **MCP adapter** (`adapters/mcp/server.py`) exposes the same operations as Model Context
  Protocol tools, on the same shared runtime, with a `tenant_id` argument per tool.
- **SDK stubs** in `sdks/python`, `sdks/go` are placeholders; `sdks/typescript` is a working client.

Credentials travel as `Authorization: Bearer tri_...` over REST and as `authorization`
metadata over gRPC. Both resolve through the same `AuthEnforcer`, so the two surfaces
cannot drift apart on who is allowed to see what.

> **Beta note:** there is no TLS. Terminate HTTPS at a reverse proxy before exposing a
> port. See [deployment.md](deployment.md).

---

## Repository Layout

```
trilith/
├── proto/                  # Protobuf schema (source of truth)
│   └── trilith.proto
├── core/                   # Python reference implementation
│   ├── proto/              # Generated gRPC/protobuf bindings (excluded from lint)
│   │   ├── trilith_pb2.py
│   │   └── trilith_pb2_grpc.py
│   ├── identity.py         # Principal — tenant / owner / session
│   ├── auth.py             # API key store + AuthEnforcer
│   ├── sqlite_backend.py   # Pluggable storage backend + schema migration
│   ├── threadsafe_backend.py
│   ├── runtime.py          # Shared Governor + stores + auth wiring
│   ├── ops.py              # Shared write/query/forget/fold/purge
│   ├── rest_app.py         # FastAPI REST gateway (:8080)
│   ├── grpc_servicer.py    # ContextManager gRPC servicer
│   ├── grpc_server.py      # gRPC server bootstrap (:50051)
│   ├── store_base.py       # Shared tier-store behaviour
│   ├── semantic.py         # Semantic tier
│   ├── procedural.py       # Procedural tier + fold()
│   ├── episodic.py         # Episodic tier + forget() cascade
│   ├── governor.py         # Ranking, distraction penalty, assemble
│   ├── privacy.py          # PolicyEngine (tenant, scope, PII, expiry)
│   ├── client.py           # Stdlib REST client
│   └── cli.py              # serve / key / tenants / purge-expired
├── adapters/
│   ├── mcp/server.py       # MCP server adapter
│   ├── langchain/          # LangChain + LangGraph tools and node
│   ├── openai_agents/      # OpenAI Agents SDK function tools
│   └── claude_sdk/         # Anthropic tool schemas + dispatcher
├── sdks/
│   ├── typescript/         # Working TypeScript client
│   ├── python/             # placeholder
│   └── go/                 # placeholder
├── examples/
│   ├── in_process_usage.py     # Single-workspace embed
│   ├── multi_tenant_usage.py   # Two customers, several users, one DB
│   └── mcp_chat.py             # Two-turn persistent memory demo
├── tests/                  # Pytest test suites
├── docs/
│   ├── quickstart.md
│   ├── deployment.md       # Tenancy, API keys, Docker, v0.1 migration
│   ├── adapters.md
│   └── architecture.md
├── pyproject.toml          # pip-installable package (trilith-core)
├── Dockerfile              # Zero-config container
└── .github/workflows/ci.yml
```
