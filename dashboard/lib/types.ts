export type Tier = "SEMANTIC" | "PROCEDURAL" | "EPISODIC";

export type Scope = "GLOBAL" | "TENANT" | "USER" | "SESSION" | "SCOPE_UNSPECIFIED";

export const TIERS: Tier[] = ["SEMANTIC", "PROCEDURAL", "EPISODIC"];
export const SCOPES: Scope[] = ["GLOBAL", "TENANT", "USER", "SESSION"];

export type Identity = {
  tenant_id: string;
  owner_id: string;
  session_id: string;
};

/** Who the browser is claiming to be. The API key wins when auth is enforced. */
export type Session = Identity & { apiKey: string };

export type Item = {
  id: string;
  tier: Tier;
  scope: Scope;
  content: string;
  provenance: string;
  created_at: string;
  expires_at: string | null;
  tenant_id: string;
  owner_id: string;
  session_id: string;
  subtask_id: string;
  /** What this row would cost an assembly, by the governor's own estimate. */
  tokens: number;
  /** Whether the current identity could actually receive it. */
  visible: boolean;
  visibility_reason: string;
};

export type ItemsPage = {
  items: Item[];
  total: number;
  limit: number;
  offset: number;
  identity: Identity;
};

export type Snapshot = {
  service: string;
  version: string;
  status: string;
  auth_enabled: boolean;
  identity: Identity;
  counts: Record<Tier, number>;
  total_items: number;
  latest_event_seq: number;
};

export type TrilithEvent = {
  seq: number;
  at: number;
  kind: "write" | "update" | "delete" | "assemble" | "forget" | "fold" | "purge" | string;
  tenant_id: string;
  actor: string;
  summary: string;
  detail: Record<string, string | number | string[]>;
};

export type AssembledItem = {
  id: string;
  tier: Tier;
  scope: Scope;
  content: string;
  tenant_id: string;
  tokens: number;
};

export type ExcludedItem = {
  id: string;
  tier: Tier;
  scope: Scope;
  reason: string;
  kind: "budget" | "policy";
  content: string;
  tokens: number;
};

export type Assembly = {
  items: AssembledItem[];
  excluded_items: ExcludedItem[];
  tokens_used: number;
  budget: number;
  task: string;
  candidates_truncated: number;
  tenant_id: string;
};

export type Subtask = { subtask_id: string; steps: number };

/** A new item being composed, or an existing one being edited. */
export type Draft = {
  id: string;
  tier: Tier;
  scope: Scope;
  content: string;
  provenance: string;
  owner_id: string;
  session_id: string;
  subtask_id: string;
  ttl_seconds: string;
};
