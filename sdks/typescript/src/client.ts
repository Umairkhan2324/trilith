/** REST client for trilith serve (Node 18+ fetch). */

export type Identity = {
  /** Isolation boundary. Ignored by the server when an API key pins one. */
  tenantId?: string;
  /** Unlocks USER-scoped items belonging to this owner. */
  ownerId?: string;
  /** Unlocks SESSION-scoped items belonging to this session. */
  sessionId?: string;
};

export type AssembleResult = {
  items: Array<{
    id: string;
    tier: string;
    scope: string;
    content: string;
    tenant_id: string;
  }>;
  tokens_used: number;
  excluded_items: Array<{ id: string; reason: string }>;
  /** Candidates dropped by the pre-rank cap; non-zero means the store is larger than one assemble can weigh. */
  candidates_truncated: number;
  tenant_id: string;
};

export type WriteResult = { success: boolean; id: string; tenant_id: string };
export type ForgetResult = {
  success: boolean;
  deleted_episodic_count: number;
  tenant_id: string;
};
export type FoldResult = {
  success: boolean;
  message: string;
  folded_count: number;
  item: { id: string; content: string } | null;
};
export type PurgeResult = { success: boolean; deleted_count: number };
export type WhoAmIResult = {
  tenant_id: string;
  owner_id: string;
  session_id: string;
  auth_enabled: boolean;
};

export type TrilithClientOptions = Identity & {
  baseUrl?: string;
  timeoutMs?: number;
  /** Required once the server has auth enabled. Falls back to TRILITH_API_KEY. */
  apiKey?: string;
};

export class TrilithClient {
  private readonly baseUrl: string;
  private readonly timeoutMs: number;
  private readonly apiKey: string;
  private readonly identity: Identity;

  constructor(options: TrilithClientOptions | string = {}) {
    // Back-compat: v0.1 took a bare base-URL string.
    const opts: TrilithClientOptions =
      typeof options === "string" ? { baseUrl: options } : options;

    this.baseUrl = (opts.baseUrl ?? "http://127.0.0.1:8080").replace(/\/$/, "");
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.apiKey = opts.apiKey ?? process.env.TRILITH_API_KEY ?? "";
    this.identity = {
      tenantId: opts.tenantId ?? process.env.TRILITH_TENANT_ID ?? undefined,
      ownerId: opts.ownerId,
      sessionId: opts.sessionId,
    };
  }

  private identityBody(overrides: Identity = {}): Record<string, string> {
    const merged = {
      tenant_id: overrides.tenantId ?? this.identity.tenantId,
      owner_id: overrides.ownerId ?? this.identity.ownerId,
      session_id: overrides.sessionId ?? this.identity.sessionId,
    };
    return Object.fromEntries(
      Object.entries(merged).filter(([, v]) => Boolean(v)),
    ) as Record<string, string>;
  }

  private headers(): Record<string, string> {
    const h: Record<string, string> = {
      "Content-Type": "application/json",
      Accept: "application/json",
    };
    if (this.apiKey) h.Authorization = `Bearer ${this.apiKey}`;
    return h;
  }

  private async request<T>(
    path: string,
    method: "GET" | "POST",
    body?: unknown,
  ): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers(),
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: ctrl.signal,
      });
      if (!res.ok) {
        throw new Error(`Trilith HTTP ${res.status}: ${await res.text()}`);
      }
      return (await res.json()) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  private post<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, "POST", body);
  }

  /** Identity the server resolved for this client — the quickest auth check. */
  whoami(): Promise<WhoAmIResult> {
    return this.request<WhoAmIResult>("/v1/whoami", "GET");
  }

  write(
    input: {
      id: string;
      content: string;
      tier?: string;
      scope?: string;
      provenance?: string;
    } & Identity,
  ): Promise<WriteResult> {
    return this.post("/v1/write", {
      id: input.id,
      content: input.content,
      tier: input.tier ?? "SEMANTIC",
      scope: input.scope ?? "TENANT",
      provenance: input.provenance ?? "",
      ...this.identityBody(input),
    });
  }

  assemble(
    task: string,
    budget = 200,
    identity: Identity = {},
  ): Promise<AssembleResult> {
    return this.post("/v1/assemble", {
      task,
      budget,
      ...this.identityBody(identity),
    });
  }

  forget(scope: string, identity: Identity = {}): Promise<ForgetResult> {
    return this.post("/v1/forget", {
      scope,
      ...this.identityBody(identity),
    });
  }

  /** Collapse a procedural sub-task's steps into one summary item. */
  fold(subtaskId: string, identity: Identity = {}): Promise<FoldResult> {
    return this.post("/v1/fold", {
      subtask_id: subtaskId,
      ...this.identityBody(identity),
    });
  }

  /** Physically delete items past their TTL. */
  purgeExpired(identity: Identity = {}): Promise<PurgeResult> {
    return this.post("/v1/purge-expired", this.identityBody(identity));
  }

  /** Bullet list ready to inject into an LLM prompt. */
  async memoryBlock(
    task: string,
    budget = 200,
    identity: Identity = {},
  ): Promise<string> {
    const ctx = await this.assemble(task, budget, identity);
    return ctx.items.map((i) => `- ${i.content}`).join("\n");
  }
}
