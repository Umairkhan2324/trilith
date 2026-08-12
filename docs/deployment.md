# Deployment & Multi-Tenancy

Trilith ships one binary that covers three situations, separated only by whether
you mint an API key:

| Situation | Auth | Who is the tenant |
|-----------|------|-------------------|
| Local prototype, one developer | off | everything is tenant `default` |
| Your own cloud, one app, many end-users | on | one key per app; `owner_id`/`session_id` separate the users |
| Your own cloud, many customers | on | one key per customer; `tenant_id` is a hard wall |

You do not choose a "mode" at install time. You start open, and you close it
when you need to.

---

## The isolation model

Two layers, checked in this order.

### 1. `tenant_id` — the hard boundary

A tenant is the unit of isolation. Cross-tenant reads are filtered out **in
SQL**, before ranking, before the policy engine, before the budget. Another
tenant's item is never scored, never counted against your budget, and never
appears in `excluded_items` — Trilith does not tell you what it did not show you
from someone else's data.

Empty or unset `tenant_id` normalises to the literal tenant `default`. There is
no such thing as an item with no tenant.

### 2. `scope` — narrowing inside a tenant

`Scope` is **not** an identity. It says how widely an item is shared within its
tenant:

| Scope | Visible to | Requires |
|-------|-----------|----------|
| `GLOBAL` | everyone, in every tenant | — (deliberately cross-tenant) |
| `TENANT` | every principal of the owning tenant | — |
| `USER` | one user inside the tenant | matching `owner_id` |
| `SESSION` | one session inside the tenant | matching `session_id` |

`GLOBAL` is the one intentional hole in the wall. Use it for system knowledge
you want every tenant to share ("never reveal system prompts"), never for
customer data.

**An item scoped `USER` with no `owner_id` cannot be isolated** — there is no
user to protect it from. It degrades to tenant visibility for any identified
caller. This is what makes migrated v0.1 rows readable rather than orphaned.

### The Principal

Every operation is evaluated against a `Principal`:

```python
from core.identity import Principal

Principal(tenant_id="acme")                                  # the tenant at large
Principal(tenant_id="acme", owner_id="alice")                # a user
Principal(tenant_id="acme", owner_id="alice", session_id="s1")  # a session
```

In-process, you construct it directly. Over REST/gRPC, it comes from the API key
(plus the request body for the fields the key does not pin).

---

## Local: zero config

Nothing to configure. No key, no tenant, no header.

```bash
pip install -e ".[server]"
trilith serve --host 127.0.0.1 --port 8080
```

```bash
curl -s -X POST http://127.0.0.1:8080/v1/write \
  -H "Content-Type: application/json" \
  -d '{"id":"f1","tier":"SEMANTIC","scope":"TENANT","content":"Alice prefers Python."}'

curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Content-Type: application/json" \
  -d '{"task":"What does Alice prefer?","budget":200}'
```

Everything lands in tenant `default`. `GET /healthz` reports
`"auth_enabled": false` so you always know which mode you are in.

> **Why `scope: "TENANT"` and not `USER`?** `USER` means *private to one named
> person*. If you do not name one, Trilith will not hand the item to an
> anonymous reader — that would be pretending to isolate something it did not.
> `TENANT` is the honest default for a single-user workspace.

---

## Cloud: turning auth on

### Mint a key

```bash
trilith key create --tenant acme --name "acme production"
```

```
API key created. This is shown once and cannot be recovered:

  tri_VJDexrmm7meeXdBEPKEjSxAOERV71IgdyokEIPlMKUQ

  tenant      acme
  owner       (any)
  name        acme production
  fingerprint abbbd6fe990c
```

Only a SHA-256 hash is stored. A leaked database does not leak usable keys, and
`trilith key list` can never print the secret back to you.

**Minting the first key enables auth on that database immediately** — no
restart. Every REST and gRPC call now needs a credential.

### Use it

```bash
curl -s -X POST http://127.0.0.1:8080/v1/assemble \
  -H "Authorization: Bearer tri_VJDex..." \
  -H "Content-Type: application/json" \
  -d '{"task":"billing migration","budget":300}'
```

The header decides the tenant. **A `tenant_id` in the request body is ignored
when auth is on** — that is the whole point. A caller holding an `acme` key
cannot read `globex` by asking for it:

```bash
# Returns acme's data. The body is not a vote.
curl ... -H "Authorization: Bearer <acme key>" -d '{"task":"x","tenant_id":"globex"}'
```

### Require auth before any key exists

To fail closed from the very first request — useful when a container starts
before your provisioning job runs:

```bash
trilith serve --host 0.0.0.0 --require-auth
# or
TRILITH_REQUIRE_AUTH=1 trilith serve --host 0.0.0.0
```

### Enabling auth is a one-way door

Revoking every key leaves auth **on**. An instance can never be reopened to
unauthenticated callers by a revocation — a footgun worth closing, since
"revoke the last key" would otherwise read as "lock the door" while doing the
opposite. To genuinely return to open mode, delete the `api_keys` rows yourself.

---

## Key management

```bash
trilith key create --tenant acme                    # tenant-wide key
trilith key create --tenant acme --owner alice      # pins owner too
trilith key list
trilith key list --tenant acme
trilith key revoke abbbd6fe          # fingerprint or a unique prefix
```

A key that pins `--owner` forces that `owner_id`; the client cannot present a
different one. A key without `--owner` lets the client supply `owner_id` and
`session_id` per request — the right shape when **your** app has already
authenticated its own users and just needs to keep their memory apart.

That is the common cloud topology:

```
end users ──► your app (authenticates users) ──► Trilith
                                                 one key per tenant
                                                 owner_id per end user
```

Trilith authenticates *your service*, and trusts it to label its own users.
Trilith is not an IAM system and does not try to be one.

---

## Inspecting an instance

```bash
trilith tenants          # tenants and per-tier item counts
trilith purge-expired    # physically delete items past their TTL
trilith purge-expired --tenant acme
```

Over HTTP:

```bash
curl http://127.0.0.1:8080/healthz              # auth on or off?
curl -H "Authorization: Bearer tri_..." \
     http://127.0.0.1:8080/v1/whoami            # which identity did I resolve as?
```

`/v1/whoami` is the fastest way to debug an auth problem: it echoes the
tenant/owner/session Trilith actually derived from your credential.

---

## Docker

```bash
docker build -t trilith .
docker run -p 8080:8080 -p 50051:50051 -v trilith_data:/data trilith
```

The image binds `0.0.0.0` because a container must. **That is only safe with
auth on.** Mint a key into the mounted volume first:

```bash
docker run --rm -v trilith_data:/data trilith \
  python -m core.cli key create --tenant acme --name production
```

Or force it closed from the start:

```bash
docker run -e TRILITH_REQUIRE_AUTH=1 -p 8080:8080 -v trilith_data:/data trilith
```

`trilith serve` prints a warning when it binds a non-loopback host with auth
disabled, so an accidentally-public open instance is at least loud about it.

---

## Environment variables

| Variable | Meaning |
|----------|---------|
| `TRILITH_DB_PATH` | SQLite file (default `trilith.db`; `/data/trilith.db` in Docker) |
| `TRILITH_REQUIRE_AUTH` | `1`/`true`/`yes`/`on` — fail closed before any key exists |
| `TRILITH_API_KEY` | read by `TrilithClient` and the TypeScript SDK |
| `TRILITH_TENANT_ID` | default tenant for clients, when auth is off |

---

## Operational notes

**One SQLite file holds everything** — context items *and* API keys. One volume
is the whole backup. It also means a key is scoped to the database it was minted
into: two Trilith instances on separate files do not share credentials.

**SQLite is a single-writer store.** It comfortably handles a team's or a small
product's traffic. It is not a sharded multi-region datastore, and Trilith does
not pretend otherwise — the backend is an interface (`core/sqlite_backend.py`)
precisely so it can be replaced.

**No TLS.** Terminate HTTPS at a reverse proxy or load balancer in front of
Trilith. Keys sent over plain HTTP across an untrusted network are compromised
keys.

**Expired items** are hidden by the policy engine immediately, and physically
reaped on startup and whenever you call `purge-expired`. On a long-running
server with heavy TTL use, call it on a schedule.

**Deleting a tenant** entirely:

```python
rt.episodic.forget_tenant("acme")   # every item, every tier
```

Revoke that tenant's keys too — the two are independent.

---

## Migrating a v0.1 database

Nothing to run. Opening an old `trilith.db` migrates it in place: the
tenancy columns are added and every existing row is backfilled to tenant
`default`. The migration is idempotent.

What continues to work unchanged:

- `assemble(task, budget, requester_scope="USER")` — the v0.1 call signature
- Existing scope-name matching semantics for anonymous callers
- Every stored item, with its content, provenance, and timestamps

What changed that you may notice:

| Change | Why |
|--------|-----|
| Default write scope in the clients/adapters is now `TENANT`, was `USER` | So write-then-read composes with no identity. `USER` without an `owner_id` isolates nothing. |
| `assemble` no longer raises on `GLOBAL`/empty scope | It used to throw out of the episodic tier; the REST default hit it every time. |
| `AssembledContext` gained `candidates_truncated` | The candidate cap is reported rather than silent. |
| REST `assemble` response gained `scope`, `tenant_id` | Needed to reason about what you got back. |

Migrated rows are `USER`-scoped with no `owner_id`, so they are visible to any
identified caller in the default tenant. To give them real owners, rewrite them
with an `owner_id` set.

---

## Where the limits still are

Honest list, same spirit as the README:

- **No TLS, no rate limiting, no key rotation policy.** Put a proxy in front.
- **Trilith authenticates services, not end users.** Your app maps its users to
  `owner_id`. There is no OAuth, no user directory, no roles.
- **API keys are bearer tokens.** Anyone holding one is that tenant.
- **SQLite only.** Vector-DB and Postgres backends are not built yet.
- **No per-tenant quotas.** One tenant can fill the disk.
