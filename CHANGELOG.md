# Changelog

Notable changes to Trilith. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project aims to
follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Releases before 0.3.0 predate this file; see the git history.

## [Unreleased] ? research hardening

- LCWP v2 research selector: source-conditioned complete-witness utility, atomic
  chain completion, exact small-instance oracle and ablations. Symbolic fact-label
  invariance is tested; natural-language extraction quality is not implied.
  [Algorithm and prior art](docs/algorithm.md).

- Composite tenant/item primary key with migration; atomic scoped writes and folds.
- Explicit administration and GLOBAL publishing capabilities; credential-pinned
  owner/session; host-bound MCP identity; policy-filtered Query responses.
- Unicode BM25 full-corpus retrieval, optional exact hybrid vector scorer, and
  coverage-per-cost selection with a singleton safeguard and tokenizer hook.
- Conservative extractive procedural summaries retain source records and scope;
  deleting/replacing a source invalidates derived memory.
- Durable content-free decision records and erasure-aware cleanup, separate from
  operational events.
- Comparative diagnostic harness, raw results, related-work review and research
  protocol. Initial synthetic results tie BM25; no novelty/superiority established.

Breaking changes and limitations: [upgrade guide](docs/upgrade-research.md).

## [0.3.0] — 2026-08-30

### Changed — read this before upgrading

Two changes alter what `assemble()` returns for the same store and the same
task. Your agent's prompt will differ after upgrading.

- **Assembly now has a relevance gate.** `Governor.min_score` (default `0.0`) is
  a score an item must *exceed* to be admitted. Previously the token budget was
  the only gate, so a generous budget injected whatever happened to fit —
  including items with zero or negative relevance to the task. Expect fewer
  items back, especially at large budgets.

  Nothing disappears silently: items stopped here are returned in
  `excluded_items` with a `Below relevance floor` reason and the score.

  To keep the old behaviour, disable the gate:

  ```bash
  trilith serve --min-score off           # or TRILITH_MIN_SCORE=off
  ```
  ```python
  Governor(min_score=float("-inf"))       # in-process
  ```

  Known limitation: TF-IDF computes IDF over the candidate set alone, so on a
  small store an item sharing only a stop word ("for", "the") with the task can
  still clear a `0.0` floor.

- **TF-IDF scores changed for any task that repeats a word.** The cosine
  numerator summed over the query's token *list*, counting a repeated term once
  per occurrence: `"python python"` scored twice `"python"`, and results could
  exceed `1.0`, which no cosine can. It now sums over distinct terms. Rankings —
  and therefore which items fit a budget — can shift for affected queries.

### Added

- **Item-level REST surface**, so a client can read and change stored context
  rather than only writing and assembling it:
  - `GET /v1/items` — browse, free-text search, filter by tier/scope, paginate.
    Each row carries its `tokens` cost and whether the current identity could
    actually receive it (`visible` / `visibility_reason`).
  - `GET /v1/items/{id}`, `PATCH /v1/items/{id}`, `DELETE /v1/items/{id}`.
    A patch sends only the fields that changed and cannot cross a tenant.
  - `GET /v1/subtasks` — procedural sub-tasks holding steps, the fold candidates.
  - `GET /v1/events` — recent operations, read with a cursor.
  - `GET /v1/tenants` — tenants holding data; just your own once auth is on.
- **`subtask_id` and `ttl_seconds` on `POST /v1/write`.** `subtask_id` makes
  `/v1/fold` reachable over REST for the first time — previously only an
  in-process caller could produce foldable steps, so the endpoint could not
  succeed. `ttl_seconds` gives `/v1/purge-expired` something to purge.
- **Activity log** (`core/events.py`) — a bounded, in-memory, tenant-scoped
  record of every mutation and assembly, whichever gateway it arrived through, so
  an agent writing over gRPC is visible next to an edit made in a browser. It is
  an operational view, not a durable audit record.
- **A fuller assembly audit.** `/v1/assemble` now returns per-item `tokens`, the
  `budget` and `task` it ran with, the effective `min_score` (`null` when the
  floor is disabled), and excluded items carrying `tier`, `scope`, `tokens`, and
  a `kind` of `policy`, `relevance`, or `budget` — three different problems, each
  fixed a different way.
- `PolicyEngine.explain(item, principal)` — the admissibility decision on its
  own, for surfaces that need to show *why* a stored row never reaches a prompt.
- `SQLiteBackend.search()`, `.stored()`, `.list_subtasks()`, and a `StoredItem`
  carrying the `subtask_id` that `ContextItem` has no field for.
- `--min-score` on `trilith serve`, and `TRILITH_MIN_SCORE`.
- The **Observatory dashboard** is now a working console rather than a read-only
  view: browse and search, write, edit and delete items in place, fold, forget,
  purge, run assemblies with the full audit, switch the tenant/owner/session it
  acts as, and watch live traffic.

### Fixed

- `POST /v1/assemble` with an explicit `"budget": null` returned a 500
  (`TypeError` from inside the budget loop). It now uses the documented default,
  and `Governor.assemble` raises a `ValueError` that names the problem.
- `/v1/fold` could never succeed over REST — see `subtask_id` above.
- `PATCH` preserves an item's `subtask_id`, so editing a step's text no longer
  orphans it from the sub-task it belongs to.

### Removed

- The dashboard's demo-telemetry fallback. When the core is unreachable the
  console now says so and shows the command to start it, instead of rendering
  invented numbers that look like live data.

### Security

- `GET /v1/items` is deliberately an **admin view of one tenant**: it returns
  stored content *unredacted*, and lists rows the policy would refuse together
  with the refusal reason, rather than hiding them. This matches what
  `/v1/dashboard` already did. `/v1/assemble` is unchanged — it still redacts PII
  and still returns only what the policy allows.
- Exclusion reasons for policy denials never carry the item's content.

### Internal

- The package version lives only in `core/__init__.py`; `pyproject.toml` reads it
  and the REST gateway reports it, so the three cannot drift.
