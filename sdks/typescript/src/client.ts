/** REST client for trilith serve (Node 18+ fetch). */

export type AssembleResult = {
  items: Array<{ id: string; tier: string; content: string }>;
  tokens_used: number;
  excluded_items: Array<{ id: string; reason: string }>;
};

export type WriteResult = { success: boolean; id: string };
export type ForgetResult = { success: boolean; deleted_episodic_count: number };

export class TrilithClient {
  constructor(
    private readonly baseUrl: string = "http://127.0.0.1:8080",
    private readonly timeoutMs: number = 30_000,
  ) {}

  private async post<T>(path: string, body: unknown): Promise<T> {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    try {
      const res = await fetch(`${this.baseUrl.replace(/\/$/, "")}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
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

  write(input: {
    id: string;
    content: string;
    tier?: string;
    scope?: string;
    provenance?: string;
  }): Promise<WriteResult> {
    return this.post("/v1/write", {
      id: input.id,
      content: input.content,
      tier: input.tier ?? "SEMANTIC",
      scope: input.scope ?? "USER",
      provenance: input.provenance ?? "",
    });
  }

  assemble(
    task: string,
    budget = 200,
    requesterScope = "USER",
  ): Promise<AssembleResult> {
    return this.post("/v1/assemble", {
      task,
      budget,
      requester_scope: requesterScope,
    });
  }

  forget(scope: string): Promise<ForgetResult> {
    return this.post("/v1/forget", { scope });
  }

  /** Bullet list ready to inject into an LLM prompt. */
  async memoryBlock(
    task: string,
    budget = 200,
    requesterScope = "USER",
  ): Promise<string> {
    const ctx = await this.assemble(task, budget, requesterScope);
    return ctx.items.map((i) => `- ${i.content}`).join("\n");
  }
}
