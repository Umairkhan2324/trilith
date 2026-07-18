# Trilith Quickstart

This guide gets you from zero to a working local Trilith context server in under 5 minutes.

## 1. Install

```bash
git clone https://github.com/Umairkhan2324/trilith.git
cd trilith

# Install the core package + server dependencies
pip install -e ".[server]"

# Compile the protobuf schema to Python bindings
python scripts/compile_proto.py
```

## 2. Start the Server

```bash
trilith serve --host 127.0.0.1 --port 8080
```

Alternatively, with Docker (zero config, SQLite storage at `/data/trilith.db`):

```bash
docker build -t trilith .
docker run -p 8080:8080 -v trilith_data:/data trilith
```

The server exposes three endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/write` | Write a context item |
| `POST` | `/v1/assemble` | Retrieve ranked context for a task |
| `POST` | `/v1/forget` | Purge all data for a scope |
| `GET` | `/healthz` | Server health check |

## 3. Write Three Facts

```bash
curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f1","tier":"SEMANTIC","scope":"USER","content":"Alice is a senior backend engineer."}'

curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f2","tier":"SEMANTIC","scope":"USER","content":"Alice primarily works with Python and Go."}'

curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f3","tier":"SEMANTIC","scope":"USER","content":"Alice is currently building a distributed tracing tool."}'
```

## 4. Assemble Context

```bash
curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Content-Type: application/json" \
  -d '{"task":"What does the user do?","budget":300,"requester_scope":"USER"}' | python -m json.tool
```

**Expected output (abbreviated):**
```json
{
  "items": [
    {"id": "f3", "tier": "SEMANTIC", "content": "Alice is currently building a distributed tracing tool."},
    {"id": "f2", "tier": "SEMANTIC", "content": "Alice primarily works with Python and Go."},
    {"id": "f1", "tier": "SEMANTIC", "content": "Alice is a senior backend engineer."}
  ],
  "tokens_used": 38,
  "excluded_items": []
}
```

Items are ranked by relevance to the task. Items that exceed the token budget are logged to `excluded_items` with an auditable reason — no silent omissions.

## 5. Forget a Scope

```bash
curl -s -X POST http://127.0.0.1:8080/v1/forget \
  -H "Content-Type: application/json" \
  -d '{"scope":"USER"}' | python -m json.tool
```

A subsequent assemble for scope `USER` returns nothing — data is **physically deleted**, not hidden by a flag.

---

## Using the MCP Adapter (Optional)

If you have an MCP-compatible agent host (e.g. Claude Desktop, Cursor):

```bash
pip install ".[mcp]"
python adapters/mcp/server.py
```

The server exposes three MCP tools: `write_context`, `assemble_context`, `forget_scope`.

See `examples/mcp_chat.py` for a standalone demo of persistent memory across simulated conversation turns.
