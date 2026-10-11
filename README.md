<div align="center">

<!-- Typing title (renders on GitHub) -->
<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=42&duration=2800&pause=1200&color=3DDC97&center=true&vCenter=true&width=680&lines=TRILITH;Context+Engineering+for+AI;+Governed+Memory.+Zero+Bloat." alt="TRILITH" />

<br/>

**Budgeted context. Three tiers. Auditable assembly.**  
Open-source context management layer for AI agents — sits between your agent and the LLM prompt.

<br/>

<!-- Badges / tags -->
[![Version](https://img.shields.io/badge/version-v0.3.0-3DDC97?style=for-the-badge&logo=semver&logoColor=white)](https://github.com/Umairkhan2324/trilith)
[![Status](https://img.shields.io/badge/status-BETA-f59e0b?style=for-the-badge)](https://github.com/Umairkhan2324/trilith)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

[![Context Management](https://img.shields.io/badge/context--management-ready-0ea5e9?style=flat-square)](docs/architecture.md)
[![Context Engineering](https://img.shields.io/badge/context--engineering-core-8b5cf6?style=flat-square)](docs/architecture.md)
[![Multi-tenant](https://img.shields.io/badge/multi--tenant-ready-16a34a?style=flat-square)](docs/deployment.md)
[![LangChain](https://img.shields.io/badge/LangChain%20%2F%20LangGraph-adapter-1C3C3C?style=flat-square)](docs/adapters.md)
[![OpenAI Agents](https://img.shields.io/badge/OpenAI%20Agents-adapter-412991?style=flat-square)](docs/adapters.md)
[![Claude](https://img.shields.io/badge/Claude%20SDK-adapter-D97706?style=flat-square)](docs/adapters.md)
[![TypeScript](https://img.shields.io/badge/TypeScript-SDK-3178C6?style=flat-square&logo=typescript&logoColor=white)](sdks/typescript)
[![MCP](https://img.shields.io/badge/MCP-adapter-111827?style=flat-square)](adapters/mcp/server.py)
[![gRPC](https://img.shields.io/badge/gRPC-50051-00ADD8?style=flat-square&logo=grpc)](proto/trilith.proto)
[![REST](https://img.shields.io/badge/REST-8080-009688?style=flat-square)](docs/quickstart.md)
[![No LLM Key](https://img.shields.io/badge/LLM%20key-not%20required-22c55e?style=flat-square)](#expect--dont-expect)

</div>

---

## Research status (unreleased hardening)

Trilith is an experimental research system. This working tree adds tenant-qualified
keys, credential-bound owner/session identity, explicit admin and GLOBAL publisher
capabilities, Unicode BM25 retrieval, coverage-per-cost packing, source-preserving
folding and durable erasure-aware decision records.

Read the **[upgrade guide](docs/upgrade-research.md)** before running an existing
client. **[Research specification](docs/research.md)** documents prior work, the
TPCC baseline and limitations. The newer **[LCWP algorithm](docs/algorithm.md)**
models complete evidence chains and shared-source invalidation; it has synthetic
oracle comparisons and explicit negative results. **[Reproducible benchmarks](benchmarks/README.md)**
currently show a tie with BM25 on synthetic fixtures, not a novel or superior
context-management technique. Language-agnostic transport does not imply universal
natural-language understanding. The broader storage/control-plane architecture
remains a roadmap.

## Why Trilith?

Agents drown in context. Trilith **governs** what enters the prompt:

| Tier | Role |
|------|------|
| **Semantic** | Durable facts |
| **Procedural** | Task steps (`fold` into summaries) |
| **Episodic** | Scoped events + cascading `forget` |

Policy → rank → drop the irrelevant → fill budget → return **included + excluded with reasons**. Policy-denied records are not exposed in response diagnostics; the durable decision log records policy outcomes.

---

## Multi-tenant, without a mode switch

The same binary runs on your laptop and in your cloud. The only difference is
whether you have minted a key.

```bash
trilith serve                                # open. everything is tenant "default"
trilith key create --tenant acme             # auth is now on, for this database
```

Once a key exists, the `Authorization` header decides the tenant — and a
`tenant_id` in the request body is **ignored**, so a caller cannot read another
tenant by asking for it.

| Layer | What it does |
|-------|--------------|
| `tenant_id` | Hard boundary. Cross-tenant rows are filtered in SQL — never ranked, never budgeted, never even listed as excluded. |
| `owner_id` / `session_id` | Narrow visibility *inside* a tenant, for `USER`- and `SESSION`-scoped items. |
| `GLOBAL` scope | The one deliberate exception: system knowledge shared by every tenant. |

Full guide → **[docs/deployment.md](docs/deployment.md)**

---

## Expect / don’t expect

**Expect**
- Local SQLite + Unicode BM25 retrieval and coverage-per-cost selection (zero external AI dependency)
- REST (`:8080`) + gRPC (`:50051`) + MCP
- **Real multi-tenancy** — tenant/user/session identity, enforced in the query layer
- **Optional API-key auth** — off by default, one command to turn on, no restart
- **Plug-and-play adapters:** LangChain/LangGraph, OpenAI Agents, Claude tools, TypeScript SDK
- Auditable `excluded_items` with reasons, and a live activity log of every operation
- Physical `forget(scope)` across tiers, confined to the caller's tenant

**Don’t expect (yet)**
- End-user IAM — Trilith authenticates *your service*; provision credentials bound to each owner/session
- TLS, rate limiting, or per-tenant quotas — put a reverse proxy in front
- Vector DB / Postgres backends
- PyPI / npm packages yet — **install from this GitHub repo** (see below)

---

## Security

- No LLM API key required for Trilith itself (it does not call a model)
- API keys are SHA-256 hashed at rest and displayed exactly once
- Enabling auth is a **one-way door**: revoking every key does not reopen the instance
- **No TLS** — terminate HTTPS at a proxy before exposing a port
- Running open (no keys) on a non-loopback host is supported but prints a startup warning

See [SECURITY.md](SECURITY.md) and [docs/deployment.md](docs/deployment.md).

---
## How Trilith Compares

There are several strong memory solutions for AI agents already. Here's an honest comparison — including where they beat Trilith.

| | **Trilith** | Mem0 | Zep | LangMem |
|---|---|---|---|---|
| **Architecture** | 3-tier (semantic / procedural / episodic) with an explicit context **budget** | LLM-driven classification, hybrid vector + graph | Temporal knowledge graph | LangGraph-native store, 3 memory types |
| **Framework lock-in** | None — LangChain, LangGraph, OpenAI Agents SDK, Claude tools, plus raw REST/gRPC/MCP | Framework-agnostic API | Framework-agnostic, strongest inside LangChain | LangGraph only |
| **Context budget enforcement** | ✅ Explicit item/token budget enforced at assembly time | Not the primary focus | Not the primary focus | Not the primary focus |
| **Audit trail on assembly** | ✅ Every `assemble()` call returns *included and excluded* items, with reasons | ❌ | ❌ | ❌ |
| **Multi-tenancy** | ✅ tenant / user / session identity, enforced in SQL, with key-bound tenants | Hosted tiers isolate by project/user | Hosted tiers isolate by user/session | Namespaces inside your own LangGraph store |
| **Self-hosted, no LLM key required** | ✅ SQLite + TF-IDF ranking, works fully offline | OSS tier yes, graph/Pro features gated behind $249/mo | Free tier limited; deeper temporal/graph features are paid | ✅ zero extra infra inside LangGraph |
| **Pricing** | Free, Apache 2.0 | Free tier + Pro from $249/mo | Free tier (limited credits) + plans from $25/mo | Free |
| **Maturity** | v0.3, early beta | Tens of thousands of stars, production track record | Strong production track record, widely deployed | Newer (2025), backed by LangChain |

### Why Trilith stands out

- **It's the only one built around a hard context budget.** Mem0, Zep, and LangMem all focus on *what* to remember. Trilith focuses on *what fits* — you set a budget, and assembly respects it every time instead of silently growing your prompt.
- **Nothing gets dropped without a reason you can see.** This is the gap every other option shares: retrieval either returns something or it doesn't, with no record of what almost made it and why it didn't. Trilith's excluded-items output closes that gap.
- **No framework tax.** You're not locked into LangGraph (LangMem) or a hosted API (Mem0 Pro, Zep). Adapters exist for the major agent stacks, plus a plain REST/gRPC/MCP surface for anything custom.
- **Fully local by default.** No LLM key, no external service call required just to manage memory — useful for anyone who doesn't want their context layer depending on a third-party API's uptime or pricing.

### Where the others currently win — and I'd rather say this than have you find out the hard way

- **Maturity and battle-testing.** Mem0 and Zep have years of production usage and tens of thousands of GitHub stars between them. Trilith is v0.3 beta — use it for prototyping and internal tools right now, not for something that can't fail.
- **Temporal/graph reasoning.** If you need relationship modeling or time-aware fact resolution across a knowledge graph, Zep is purpose-built for that today. Trilith doesn't do this yet.
- **Hosted, zero-ops option.** Mem0 and Zep offer managed cloud tiers. Trilith is self-hosted only right now — that's a feature for some teams and a dealbreaker for others.
- **Identity infrastructure.** Trilith's tenancy is real and enforced, but it authenticates services, not end users. Hosted competitors hand you user management; here your app owns that and passes Trilith an `owner_id`.
- **Scale ceiling.** SQLite is a single-writer store. Fine for a team or a small product, not for a sharded multi-region workload.

If your priority is transparency and hard budget control over your agent's context, Trilith is built exactly for that. If you need a mature, hosted, graph-native memory system today, Mem0 or Zep are the safer production choice — and I'd rather send you there than oversell what's still a beta.
---
## Plug-and-play (30 seconds)

```bash
pip install -e ".[server]"
trilith serve --host 127.0.0.1 --port 8080
```

| Stack | Drop-in |
|-------|---------|
| **Any Python** | `from core.client import TrilithClient` |
| **LangChain / LangGraph** | `from adapters.langchain import make_trilith_tools, make_assemble_node` |
| **OpenAI Agents SDK** | `from adapters.openai_agents import make_trilith_tools` |
| **Claude / Anthropic** | `from adapters.claude_sdk import TRILITH_TOOL_SCHEMAS, run_trilith_tool` |
| **TypeScript** | `import { TrilithClient } from "@trilith/sdk"` (see `sdks/typescript`) |

Bind identity once, on the client — not per tool call, so an agent can't talk
itself into another tenant:

```python
c = TrilithClient(api_key="tri_...", owner_id="alice")
tools = make_trilith_tools(c)
```

Full copy-paste examples → **[docs/adapters.md](docs/adapters.md)**

---

## Install (from GitHub — not on PyPI yet)

```bash
git clone https://github.com/Umairkhan2324/trilith.git
cd trilith
pip install -e ".[server]"
```

Optional: `pip install -e ".[mcp]"` or `pip install -e ".[adapters]"`

## Run (localhost)

```bash
trilith serve --host 127.0.0.1 --port 8080 --grpc-port 50051
```

Docker (binds `0.0.0.0`, so turn auth on — see [deployment](docs/deployment.md)):

```bash
docker build -t trilith .
docker run -e TRILITH_REQUIRE_AUTH=1 -p 8080:8080 -p 50051:50051 -v trilith_data:/data trilith
```

### Observatory dashboard

The optional Next.js console is a working surface over the same REST API an
agent uses — browse and search the store, write, edit, and delete items in
place, fold a sub-task, forget a scope, run real assemblies and read the full
inclusion/exclusion audit, switch the tenant/owner/session you act as, and watch
a live feed of every operation on the instance:

```bash
cd dashboard
npm install
npm run dev
```

Open `http://localhost:3000` while `trilith serve` is running. See
[`dashboard/README.md`](dashboard/README.md) for configuration.

If another application already owns port 3000, use `npm run dev -- -p 3001`.
When it cannot reach the core it says so and tells you how to start it — it
never draws placeholder numbers.

## Call it (REST)

```bash
curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f1","tier":"SEMANTIC","scope":"TENANT","content":"Alice prefers Python."}'

curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Content-Type: application/json" \
  -d '{"task":"What does Alice prefer?","budget":200}'
```

With auth on, add `-H "Authorization: Bearer tri_..."` — the key decides the tenant.

| Endpoint | Purpose |
|----------|---------|
| `POST /v1/write` | Store an item in a tier |
| `POST /v1/assemble` | Budgeted, ranked context + exclusion audit |
| `POST /v1/forget` | Physical purge of a scope, within your tenant |
| `POST /v1/fold` | Collapse a sub-task's procedural steps into one summary |
| `POST /v1/purge-expired` | Reap items past their TTL |
| `GET /v1/items` | Browse, search, filter, and page the tenant's stored context |
| `PATCH /v1/items/{id}` | Edit one item in place |
| `DELETE /v1/items/{id}` | Delete one item |
| `GET /v1/subtasks` | Procedural sub-tasks holding steps — the fold candidates |
| `GET /v1/events` | Recent operations on this instance, read with a cursor |
| `GET /v1/whoami` | Which identity did Trilith resolve you as? |
| `GET /v1/dashboard` | Tenant-scoped counts and recent activity for dashboards |
| `GET /healthz` | Liveness + whether auth is on |

## Call it (gRPC)

Proto service: `trilith.ContextManager` (`Write` / `Query` / `Assemble` / `Forget` /
`Fold` / `PurgeExpired`) on port **50051**. Auth travels as `authorization`
metadata. See [`proto/trilith.proto`](proto/trilith.proto) and [`tests/test_grpc.py`](tests/test_grpc.py).

## Where to use it

Wire **assemble → prompt** in your agent loop (or MCP tools).  
Trilith = memory + governance — not an agent framework, not an LLM.

---

## Docs

- [Quickstart](docs/quickstart.md) — imports, agent loop, REST/gRPC, and dashboard
- [Observatory dashboard](dashboard/README.md) — live console, configuration, and ports
- [**Deployment & multi-tenancy**](docs/deployment.md) — tenants, API keys, Docker, migrating from v0.1
- [**Adapters (plug-and-play)**](docs/adapters.md) — LangChain, OpenAI Agents, Claude, TypeScript
- [Architecture](docs/architecture.md)
- [**Changelog**](CHANGELOG.md) — what changed in v0.3.0, and what to do before upgrading
- Demos: [`examples/in_process_usage.py`](examples/in_process_usage.py), [`examples/multi_tenant_usage.py`](examples/multi_tenant_usage.py), [`examples/adapter_snippets.py`](examples/adapter_snippets.py)

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

<div align="center">

**TRILITH** · context engineering · v0.3.0 beta

</div>
