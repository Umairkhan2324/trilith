/**
 * Typed client for Trilith Core.
 *
 * Every call carries the console's current identity. Two paths exist because
 * the core resolves identity two ways: an `Authorization` header (which pins
 * the tenant and cannot be overridden) or, in open local mode, plain
 * tenant/owner/session fields. Sending both is safe - the key wins - so the
 * console always sends what it has and lets the core decide.
 *
 * Requests go to /trilith/*, which next.config.ts rewrites onto the REST
 * gateway, so the browser never needs CORS.
 */

import type {
  Assembly,
  Draft,
  Item,
  ItemsPage,
  Scope,
  Session,
  Snapshot,
  Subtask,
  Tier,
  TrilithEvent,
} from "./types";

const BASE = "/trilith";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

/** Thrown when the core is not answering at all - a different problem to a 4xx. */
export class OfflineError extends Error {
  constructor() {
    super("Trilith Core is not reachable");
    this.name = "OfflineError";
  }
}

function authHeaders(session: Session): HeadersInit {
  return session.apiKey ? { Authorization: `Bearer ${session.apiKey}` } : {};
}

/** Identity as query params, for GET and DELETE. Empty fields are omitted. */
function identityParams(session: Session): Record<string, string> {
  const params: Record<string, string> = {};
  if (session.tenant_id) params.tenant_id = session.tenant_id;
  if (session.owner_id) params.owner_id = session.owner_id;
  if (session.session_id) params.session_id = session.session_id;
  return params;
}

/** Identity as body fields, for POST and PATCH. */
function identityBody(session: Session): Record<string, string> {
  return identityParams(session);
}

function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new OfflineError();
  }

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (body?.detail) detail = String(body.detail);
    } catch {
      // A non-JSON error body is still an error; the status line will do.
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function get<T>(path: string, session: Session, params: Record<string, string | number | undefined> = {}) {
  return request<T>(`${path}${query({ ...identityParams(session), ...params })}`, {
    headers: authHeaders(session),
  });
}

function send<T>(method: string, path: string, session: Session, body: object) {
  return request<T>(path, {
    method,
    headers: { "Content-Type": "application/json", ...authHeaders(session) },
    body: JSON.stringify({ ...identityBody(session), ...body }),
  });
}

/** Blank strings mean "unset" in a form but "clear this field" in a patch. */
function ttlOrUndefined(value: string): number | undefined {
  const trimmed = value.trim();
  if (trimmed === "") return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) ? Math.trunc(parsed) : undefined;
}

export const api = {
  health(session: Session) {
    return get<{ status: string; version: string; auth_enabled: boolean }>("/healthz", session);
  },

  snapshot(session: Session) {
    return get<Snapshot>("/v1/dashboard", session);
  },

  items(
    session: Session,
    options: { tier?: Tier | ""; scope?: Scope | ""; q?: string; limit?: number; offset?: number } = {},
  ) {
    return get<ItemsPage>("/v1/items", session, {
      tier: options.tier || undefined,
      scope: options.scope || undefined,
      q: options.q || undefined,
      limit: options.limit ?? 50,
      offset: options.offset ?? 0,
    });
  },

  item(session: Session, id: string) {
    return get<Item>(`/v1/items/${encodeURIComponent(id)}`, session);
  },

  subtasks(session: Session) {
    return get<{ subtasks: Subtask[] }>("/v1/subtasks", session);
  },

  tenants(session: Session) {
    return get<{ tenants: string[]; scoped: boolean }>("/v1/tenants", session);
  },

  events(session: Session, after: number, limit = 100) {
    return get<{ events: TrilithEvent[]; latest_seq: number }>("/v1/events", session, {
      after,
      limit,
    });
  },

  write(session: Session, draft: Draft) {
    return send<{ success: boolean; id: string; tenant_id: string }>("POST", "/v1/write", session, {
      id: draft.id,
      tier: draft.tier,
      scope: draft.scope,
      content: draft.content,
      provenance: draft.provenance,
      owner_id: draft.owner_id || undefined,
      session_id: draft.session_id || undefined,
      subtask_id: draft.subtask_id || undefined,
      ttl_seconds: ttlOrUndefined(draft.ttl_seconds),
    });
  },

  patch(session: Session, id: string, changes: Partial<Draft>) {
    const body: Record<string, unknown> = {};
    for (const key of ["content", "tier", "scope", "provenance", "owner_id", "session_id", "subtask_id"] as const) {
      if (changes[key] !== undefined) body[key] = changes[key];
    }
    if (changes.ttl_seconds !== undefined) {
      const ttl = ttlOrUndefined(changes.ttl_seconds);
      if (ttl !== undefined) body.ttl_seconds = ttl;
    }
    return send<{ success: boolean; id: string; changed: string[]; item: Item | null }>(
      "PATCH",
      `/v1/items/${encodeURIComponent(id)}`,
      session,
      body,
    );
  },

  remove(session: Session, id: string) {
    return request<{ success: boolean; id: string }>(
      `/v1/items/${encodeURIComponent(id)}${query(identityParams(session))}`,
      { method: "DELETE", headers: authHeaders(session) },
    );
  },

  assemble(session: Session, task: string, budget: number) {
    return send<Assembly>("POST", "/v1/assemble", session, { task, budget });
  },

  fold(session: Session, subtaskId: string) {
    return send<{ success: boolean; message: string; folded_count: number }>(
      "POST",
      "/v1/fold",
      session,
      { subtask_id: subtaskId },
    );
  },

  forget(session: Session, scope: Scope) {
    return send<{ success: boolean; deleted_episodic_count: number }>("POST", "/v1/forget", session, {
      scope,
    });
  },

  purgeExpired(session: Session) {
    return send<{ success: boolean; deleted_count: number }>("POST", "/v1/purge-expired", session, {});
  },
};
