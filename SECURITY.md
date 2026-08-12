# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.2.x (beta) | Yes — self-hosted, behind your own TLS termination |
| 0.1.x | No — upgrade; databases migrate automatically |

## What Trilith protects

- **Tenant isolation.** `tenant_id` is filtered in SQL. Another tenant's row is never
  fetched, ranked, budgeted, or listed as excluded. `Scope.GLOBAL` is the one deliberate
  cross-tenant exception.
- **Scope narrowing.** `USER` and `SESSION` items are withheld unless the caller's
  `owner_id` / `session_id` matches.
- **Unforgeable tenants.** With auth on, the API key determines the tenant and a
  `tenant_id` in the request body is discarded, not merged.
- **API keys at rest.** SHA-256 hashed, displayed exactly once, never recoverable from
  the database or from `trilith key list`.
- **One-way door.** Revoking every key does not reopen an instance to unauthenticated
  callers.
- **PII redaction.** Emails, phone numbers, and national ID patterns are redacted from
  assembled content, on a copy — stored items are never mutated.

## What Trilith does not protect

- **No TLS.** Terminate HTTPS at a reverse proxy. Keys sent over plain HTTP across an
  untrusted network are compromised keys.
- **No end-user IAM.** Trilith authenticates *your service*, not your users. Your app
  authenticates its users and passes an `owner_id`.
- **API keys are bearer tokens.** Anyone holding one is that tenant. There is no
  rotation policy, expiry, or scope beyond tenant/owner.
- **No rate limiting or per-tenant quotas.** One tenant can exhaust the disk.
- **PII redaction is regex-based.** It is a safety net, not a compliance control, and it
  will miss formats it does not know.

## Deployment expectations

- Auth is **off** by default so local development needs no credentials. Everything lands
  in tenant `default`.
- Minting the first key (`trilith key create --tenant <id>`) enables auth immediately,
  with no restart. `--require-auth` / `TRILITH_REQUIRE_AUTH=1` fails closed beforehand.
- `trilith serve` prints a warning when binding a non-loopback host with auth disabled.
- Do not expose `8080` / `50051` publicly without both auth **and** a TLS proxy.
- Trilith does not require an LLM API key; do not put provider secrets in this repo.

See [docs/deployment.md](docs/deployment.md) for the full guide.

## Reporting a vulnerability

Open a GitHub issue with the label `security` **without** including secrets or private data, or email the maintainers via the GitHub profile linked on the repo.

Please include: Trilith version, reproduction steps, and impact — not exploit payloads against third-party systems.
