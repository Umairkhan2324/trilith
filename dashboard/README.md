# Trilith Observatory

The Observatory is Trilith's Next.js operations console. It makes the context
pipeline visible *and* editable without touching the SQLite database directly —
everything it does goes through the same REST gateway an agent would use.

## What you can do from it

**Read**

- inventory per tier, and the whole store searchable by content, id, provenance,
  or sub-task;
- the token cost of every item, by the governor's own estimate;
- for any item the current identity could *not* receive, the policy's reason —
  the row stays in the list, marked, rather than quietly disappearing.

**Change**

- write a new item (tier, scope, content, provenance, owner, session, sub-task,
  TTL);
- edit any item in place — only the fields you actually changed are sent;
- delete a single item (two-step, because the delete is physical);
- fold a sub-task's steps into one summary, forget a whole scope, purge expired
  items.

**Watch**

- an assembly workbench that runs the real governor: a budget meter showing what
  each admitted item costs, then everything excluded, split into what the budget
  pushed out and what the policy refused;
- a live activity feed of every operation on the instance — including writes made
  by an agent over gRPC or MCP while the page is open;
- an identity switcher for tenant, owner, and session, so you can watch the same
  store answer a different caller.

## Run locally

Start both processes from the repository root:

```powershell
# Terminal 1: REST and gRPC core
trilith serve --host 127.0.0.1 --port 8080 --grpc-port 50051

# Terminal 2: web console
cd dashboard
npm install
npm run dev
```

Open <http://localhost:3000>. Next.js proxies `/trilith/*` requests to the REST
gateway, so browser CORS configuration is not required.

Set a different core address before starting Next.js when necessary:

```powershell
$env:TRILITH_API_URL = "http://127.0.0.1:8081"
npm run dev
```

### If port 3000 is occupied

Run the dashboard on another port:

```powershell
npm run dev -- -p 3001
```

To identify the owner of port 3000 on Windows:

```powershell
netstat -ano | Select-String ':3000'
Get-Process -Id <PID>
```

Stop only the process you identified with `Stop-Process -Id <PID>`. On Linux or
macOS, use `lsof -iTCP:3000 -sTCP:LISTEN` to identify it first.

## Connection behavior

The badge reads **Core connected** when `/v1/dashboard` answers. When it does
not, the console says **Core unreachable** and shows the command to start the
core. It does not fall back to sample data: a dashboard that renders plausible
numbers while disconnected teaches you to distrust every number on it.

An empty tenant offers to write a small set of real starter items, so there is
something to rank, fold, and forget. Those are ordinary writes, not a preview.

## Identity and keys

The identity chip in the top bar opens tenant / owner / session fields and an API
key box.

- **Auth off (local default):** the fields are taken at face value. Switching
  owner is the quickest way to see scope narrowing actually working.
- **Auth on:** the key decides the tenant and the tenant field is ignored, which
  the panel says on screen. Owner and session still narrow inside it.

The key is kept in this browser's `localStorage` and sent only to your own core.
Never put a key in a `NEXT_PUBLIC_*` environment variable — that ships it to
everyone who loads the page.

## What it is not

The activity feed is in-memory and bounded (a few hundred recent events, per
process). It shows live traffic; it is not a durable audit log, and it starts
empty after a restart.

The browse and edit endpoints are an *admin* view of one tenant: stored content
is returned unredacted, and rows the policy would refuse are listed with the
reason. `/v1/assemble` is unchanged — it still redacts PII and still returns only
what the policy allows.

## Production build

```powershell
npm ci
npm run build
npm start
```

The dashboard production build is also checked by the repository's GitHub Actions.
