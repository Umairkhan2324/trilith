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
c.write("f1", "Alice prefers Python.")
memory = c.memory_block("What does Alice prefer?", budget=300)
prompt = f"Known context:\n{memory}\n\nUser: What does Alice prefer?"
```

---

## LangChain / LangGraph

```bash
pip install -e ".[server,langchain]"
```

```python
from adapters.langchain import make_trilith_tools, make_assemble_node

tools = make_trilith_tools()          # bind to a LangChain agent
assemble = make_assemble_node()       # LangGraph node

# Graph sketch:
# state = assemble({"input": user_message})
# prompt = system + state["trilith_memory"] + user_message
```

---

## OpenAI Agents SDK

```bash
pip install -e ".[server,openai-agents]"
```

```python
from agents import Agent
from adapters.openai_agents import make_trilith_tools

agent = Agent(
    name="MemoryAgent",
    instructions="Call trilith_assemble before answering when you need memory.",
    tools=make_trilith_tools(),
)
```

---

## Claude / Anthropic SDK

```bash
pip install -e ".[server,claude]"
```

```python
import anthropic
from adapters.claude_sdk import TRILITH_TOOL_SCHEMAS, run_trilith_tool

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
        result = run_trilith_tool(block.name, block.input)
        # send tool_result back in the next messages.create(...)
```

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

Tools: `write_context`, `assemble_context`, `forget_scope`.

---

## Requirement

All adapters talk to **`trilith serve`** over REST. Keep the server running locally (or Docker). Auth is not enabled yet — localhost only for beta.
