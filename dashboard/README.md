# Trilith Observatory

The Observatory is Trilith's Next.js operations console. It makes the context
pipeline visible without reading the SQLite database directly.

It shows:

- inventory totals for semantic, procedural, and episodic memory;
- recent context with scope and provenance;
- resolved tenant, owner, session, authentication, and runtime state;
- an assembly workbench for testing tasks and token budgets; and
- selected items, policy exclusions, and tokens consumed by an assembly.

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

The badge says **Core connected** when `/v1/dashboard` is reachable. Otherwise,
the interface explicitly switches to **Demo telemetry** and the assembly workbench
returns illustrative data. Demo mode is not evidence that Trilith Core is running.

The current local dashboard targets Trilith's open development mode. API-key entry
for an auth-enforced deployment is not yet exposed in the browser UI; never place a
secret in a `NEXT_PUBLIC_*` environment variable.

## Production build

```powershell
npm ci
npm run build
npm start
```

The dashboard production build is also checked by the repository's GitHub Actions.
