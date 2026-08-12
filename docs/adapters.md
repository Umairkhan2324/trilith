# Plug-and-play adapters

Trilith’s core is Python, but **you don’t need to touch the core** for day-to-day use.  
Start `trilith serve`, then drop in an adapter.

```bash
pip install -e ".[server]"
trilith serve --host 127.0.0.1 --port 8080
```

---

## Shared client (any Python agent)

```python
from core.client import TrilithClient

c = TrilithClient()  # http://127.0.0.1:8080
c.write("f1", "Alice prefers Python.")          # scope defaults to TENANT
memory = c.memory_block("What does Alice prefer?", budget=300)
prompt = f"Known context:\n{memory}\n\nUser: What does Alice prefer?"
```

Also available: `c.fold(subtask_id)`, `c.purge_expired()`, `c.whoami()`.

### Identity belongs on the client, not the tool

Bind tenant and user **once**, when you construct the client. Every adapter below
takes a client, and none of them expose `tenant_id` as a tool argument — so a model
cannot name a tenant of its own choosing in a tool call.

```python
c = TrilithClient(
    api_key="tri_...",   # or the TRILITH_API_KEY env var
    owner_id="alice",    # this end user
)
```

With auth on, the key decides the tenant server-side and any `tenant_id` in the body is
ignored. Serving many users from one process? Override per call instead:

```python
c.write("pref", "Alice prefers Python.", scope="USER", owner_id="alice")
c.assemble("preferences?", owner_id="alice", session_id="s1")
```

See **[deployment.md](deployment.md)** for minting keys.

---

## LangChain / LangGraph

```bash
pip install -e ".[server,langchain]"
```

```python
from core.client import TrilithClient
from adapters.langchain import make_trilith_tools, make_assemble_node

c = TrilithClient(api_key="tri_...", owner_id="alice")

tools = make_trilith_tools(c)         # trilith_write / assemble / fold / forget
assemble = make_assemble_node(c)      # LangGraph node

# Graph sketch:
# state = assemble({"input": user_message})
# prompt = system + state["trilith_memory"] + user_message
```

`make_assemble_node` reads `session_id` out of the graph state by default, so a graph
serving many concurrent conversations keeps their SESSION-scoped memory apart:

```python
assemble = make_assemble_node(c, session_key="session_id")
state = assemble({"input": "what were we doing?", "session_id": "conv-42"})
```

---

## OpenAI Agents SDK

```bash
pip install -e ".[server,openai-agents]"
```

```python
from agents import Agent
from core.client import TrilithClient
from adapters.openai_agents import make_trilith_tools

c = TrilithClient(api_key="tri_...", owner_id="alice")

agent = Agent(
    name="MemoryAgent",
    instructions="Call trilith_assemble before answering when you need memory.",
    tools=make_trilith_tools(c),
)
```

---

## Claude / Anthropic SDK

```bash
pip install -e ".[server,claude]"
```

```python
import anthropic
from core.client import TrilithClient
from adapters.claude_sdk import TRILITH_TOOL_SCHEMAS, run_trilith_tool

trilith = TrilithClient(api_key="tri_...", owner_id="alice")
client = anthropic.Anthropic()
msg = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    tools=TRILITH_TOOL_SCHEMAS,
    messages=[{"role": "user", "content": "What do you know about Alice?"}],
)

# When Claude returns tool_use blocks:
for block in msg.content:
    if block.type == "tool_use":
        result = run_trilith_tool(block.name, block.input, client=trilith)
        # send tool_result back in the next messages.create(...)
```

Tools: `trilith_write`, `trilith_assemble`, `trilith_fold`, `trilith_forget`. None of
them accept a tenant — that comes from the client you pass in.

---

## TypeScript / Node

```bash
cd sdks/typescript
npm install
# use from source or npm run build
```

```typescript
import { TrilithClient } from "@trilith/sdk";
// or: import { TrilithClient } from "./sdks/typescript/src/index.ts";

const trilith = new TrilithClient("http://127.0.0.1:8080");
await trilith.write({ id: "f1", content: "Alice ships React apps." });
const memory = await trilith.memoryBlock("What does Alice ship?", 300);
const prompt = `Known context:\n${memory}\n\nUser: What does Alice ship?`;
```

Package name: `@trilith/sdk` (publish to npm when ready). Until then, import from the repo path.

---

## MCP

```bash
pip install -e ".[mcp]"
python adapters/mcp/server.py
```

Tools: `write_context`, `assemble_context`, `fold_procedural`, `forget`,
`purge_expired_items`.

Each takes a `tenant_id` (default `"default"`), so one MCP host can serve several
isolated workspaces from one database file. The MCP adapter does not use API keys — an
MCP host is a single trusted process — but it runs on the same shared runtime as REST
and gRPC, so migrations, thread-safety, and TTL reaping all behave identically.

---

## Requirement

All adapters except MCP talk to **`trilith serve`** over REST.

- **Local:** no key needed. `trilith serve --host 127.0.0.1` and you are done.
- **Shared or public:** mint a key (`trilith key create --tenant <id>`), pass it as
  `api_key`, and terminate TLS at a proxy in front. There is no TLS in Trilith itself.

Full guide: **[deployment.md](deployment.md)**.
