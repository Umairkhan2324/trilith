# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| 0.1.x (beta) | Local / trusted-network testing only |

## Beta assumptions

- REST and gRPC **have no authentication**.
- Default bind is **`127.0.0.1`** (localhost).
- Do **not** expose ports `8080` / `50051` to the public internet.
- Trilith does not require an LLM API key; do not put provider secrets in this repo.

## Reporting a vulnerability

Open a GitHub issue with the label `security` **without** including secrets or private data, or email the maintainers via the GitHub profile linked on the repo.

Please include: Trilith version, reproduction steps, and impact — not exploit payloads against third-party systems.
