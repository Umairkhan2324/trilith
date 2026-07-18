# Trilith

**Alpha (v0.1)** — open-source context management for AI agents: three memory tiers, budgeted assembly, privacy filtering, and auditable exclusions. No LLM or API key required to run.

Trilith sits **between your agent and the LLM prompt**. You write facts/events into stores; before each model call you `assemble` under a token budget and inject only the selected items.

## Expect / don’t expect

**Expect**
- Local SQLite + TF-IDF ranking (zero external AI dependency)
- REST (`:8080`) + gRPC (`:50051`) + MCP adapter
- Auditable `excluded_items` with reasons
- Physical `forget(scope)` across tiers

**Don’t expect (yet)**
- Production multi-tenant IAM / real tenant IDs (scopes are coarse enums)
- Vector DB backends, LangChain / OpenAI Agents adapters (stubs)
- Auth on REST/gRPC (local-first; put a gateway in front for shared deploys)
- Published PyPI package until you publish `trilith-core` (install from git for now)

## Install

```bash
git clone https://github.com/Umairkhan2324/trilith.git
cd trilith
pip install -e ".[server]"
```

Optional MCP extras: `pip install -e ".[mcp]"`

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

Proto service: `trilith.ContextManager` (`Write` / `Query` / `Assemble` / `Forget`) on port **50051**. See `proto/trilith.proto` and `tests/test_grpc.py`.

## Where to use it

Wire **assemble → prompt** in your agent loop (or MCP tools). Trilith is memory + governance, not an agent framework and not an LLM.

## Docs

- [Quickstart](docs/quickstart.md)
- [Architecture](docs/architecture.md)
- MCP demo: `examples/mcp_chat.py`

## License

Apache License 2.0 — see [LICENSE](LICENSE).
