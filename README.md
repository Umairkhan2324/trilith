<div align="center">

<!-- Typing title (renders on GitHub) -->
<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=700&size=42&duration=2800&pause=1200&color=3DDC97&center=true&vCenter=true&width=680&lines=TRILITH;Context+Engineering+for+AI;Governed+Memory.+Zero+Bloat." alt="TRILITH" />

<br/>

**Budgeted context. Three tiers. Auditable assembly.**  
Open-source context management layer for AI agents — sits between your agent and the LLM prompt.

<br/>

<!-- Badges / tags -->
[![Version](https://img.shields.io/badge/version-v0.1.0-3DDC97?style=for-the-badge&logo=semver&logoColor=white)](https://github.com/Umairkhan2324/trilith)
[![Status](https://img.shields.io/badge/status-BETA-f59e0b?style=for-the-badge)](https://github.com/Umairkhan2324/trilith)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue?style=for-the-badge)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)

[![Context Management](https://img.shields.io/badge/context--management-ready-0ea5e9?style=flat-square)](docs/architecture.md)
[![Context Engineering](https://img.shields.io/badge/context--engineering-core-8b5cf6?style=flat-square)](docs/architecture.md)
[![LangChain](https://img.shields.io/badge/LangChain%20%2F%20LangGraph-adapter-1C3C3C?style=flat-square)](docs/adapters.md)
[![OpenAI Agents](https://img.shields.io/badge/OpenAI%20Agents-adapter-412991?style=flat-square)](docs/adapters.md)
[![Claude](https://img.shields.io/badge/Claude%20SDK-adapter-D97706?style=flat-square)](docs/adapters.md)
[![TypeScript](https://img.shields.io/badge/TypeScript-SDK-3178C6?style=flat-square&logo=typescript&logoColor=white)](sdks/typescript)
[![MCP](https://img.shields.io/badge/MCP-adapter-111827?style=flat-square)](adapters/mcp/server.py)
[![gRPC](https://img.shields.io/badge/gRPC-50051-00ADD8?style=flat-square&logo=grpc)](proto/trilith.proto)
[![REST](https://img.shields.io/badge/REST-8080-009688?style=flat-square)](docs/quickstart.md)
[![No LLM Key](https://img.shields.io/badge/API%20key-not%20required-22c55e?style=flat-square)](#expect--dont-expect)

</div>

---

## Why Trilith?

Agents drown in context. Trilith **governs** what enters the prompt:

| Tier | Role |
|------|------|
| **Semantic** | Durable facts |
| **Procedural** | Task steps (`fold` into summaries) |
| **Episodic** | Scoped events + cascading `forget` |

Policy → rank → fill budget → return **included + excluded with reasons**. No silent drops.

---

## Expect / don’t expect

**Expect**
- Local SQLite + TF-IDF ranking (zero external AI dependency)
- REST (`:8080`) + gRPC (`:50051`) + MCP
- **Plug-and-play adapters:** LangChain/LangGraph, OpenAI Agents, Claude tools, TypeScript SDK
- Auditable `excluded_items` with reasons
- Physical `forget(scope)` across tiers

**Don’t expect (yet)**
- Production multi-tenant IAM / real tenant IDs (scopes are coarse enums)
- Vector DB backends
- Auth on REST/gRPC (local-first; put a gateway in front for shared deploys)
- PyPI / npm publish until you release (install from git / path for now)

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

Full copy-paste examples → **[docs/adapters.md](docs/adapters.md)**

---

## Install

```bash
git clone https://github.com/Umairkhan2324/trilith.git
cd trilith
pip install -e ".[server]"
```

Optional MCP: `pip install -e ".[mcp]"`

## Run

```bash
trilith serve --host 127.0.0.1 --port 8080 --grpc-port 50051
```

Docker:

```bash
docker build -t trilith .
docker run -p 8080:8080 -p 50051:50051 -v trilith_data:/data trilith
```

## Call it (REST)

```bash
curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f1","tier":"SEMANTIC","scope":"USER","content":"Alice prefers Python."}'

curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Content-Type: application/json" \
  -d '{"task":"What does Alice prefer?","budget":200,"requester_scope":"USER"}'
```

## Call it (gRPC)

Proto service: `trilith.ContextManager` (`Write` / `Query` / `Assemble` / `Forget`) on port **50051**.  
See `proto/trilith.proto` and `tests/test_grpc.py`.

## Where to use it

Wire **assemble → prompt** in your agent loop (or MCP tools).  
Trilith = memory + governance — not an agent framework, not an LLM.

---

## Docs

- [Quickstart](docs/quickstart.md) — imports, agent loop, REST/gRPC
- [**Adapters (plug-and-play)**](docs/adapters.md) — LangChain, OpenAI Agents, Claude, TypeScript
- [Architecture](docs/architecture.md)
- Demos: [`examples/in_process_usage.py`](examples/in_process_usage.py), [`examples/adapter_snippets.py`](examples/adapter_snippets.py)

## License

Apache License 2.0 — see [LICENSE](LICENSE).

---

<div align="center">

**TRILITH** · context engineering · v0.1.0 beta

</div>
