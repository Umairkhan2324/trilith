import type { Draft } from "./types";

/**
 * A starter set for an empty tenant.
 *
 * These are written through the ordinary write path - they are real rows, not
 * a preview - and they are chosen so every operation on the page has something
 * to act on: facts to rank, steps sharing a sub-task to fold, a session-scoped
 * event to forget, and an item that expires so purging does something.
 */
export const SAMPLE_CONTEXT: Draft[] = [
  {
    id: "sample-preference",
    tier: "SEMANTIC",
    scope: "TENANT",
    content: "The research agent should answer concisely and always cite the source of a claim.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "",
    ttl_seconds: "",
  },
  {
    id: "sample-stack",
    tier: "SEMANTIC",
    scope: "TENANT",
    content:
      "Trilith runs on SQLite with TF-IDF ranking. No embedding service and no LLM key are required.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "",
    ttl_seconds: "",
  },
  {
    id: "sample-policy",
    tier: "SEMANTIC",
    scope: "GLOBAL",
    content: "Episodic memory never crosses a tenant boundary, even when marked global.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "",
    ttl_seconds: "",
  },
  {
    id: "sample-private-note",
    tier: "SEMANTIC",
    scope: "USER",
    content: "Maya prefers to review long outputs as a diff rather than as prose.",
    provenance: "sample",
    owner_id: "maya",
    session_id: "",
    subtask_id: "",
    ttl_seconds: "",
  },
  {
    id: "sample-step-1",
    tier: "PROCEDURAL",
    scope: "TENANT",
    content: "Read the evaluation set and grouped the failures by retrieval tier.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "eval-sweep",
    ttl_seconds: "",
  },
  {
    id: "sample-step-2",
    tier: "PROCEDURAL",
    scope: "TENANT",
    content: "Re-ran the sweep at budgets of 200, 400, and 800 tokens and recorded token usage.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "eval-sweep",
    ttl_seconds: "",
  },
  {
    id: "sample-step-3",
    tier: "PROCEDURAL",
    scope: "TENANT",
    content: "Found that distraction penalties dominate below a 200 token budget.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "eval-sweep",
    ttl_seconds: "",
  },
  {
    id: "sample-session-event",
    tier: "EPISODIC",
    scope: "SESSION",
    content: "The operator asked for a summary of yesterday's evaluation run.",
    provenance: "sample",
    owner_id: "",
    session_id: "research-42",
    subtask_id: "",
    ttl_seconds: "",
  },
  {
    id: "sample-expiring",
    tier: "EPISODIC",
    scope: "TENANT",
    content: "Temporary note: the staging index is rebuilding and results may lag.",
    provenance: "sample",
    owner_id: "",
    session_id: "",
    subtask_id: "",
    ttl_seconds: "900",
  },
];
