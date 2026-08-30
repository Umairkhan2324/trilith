"use client";

import { Activity, ArrowUpRight, BookOpen, Braces, CircleCheck, Clock3, Database, Fingerprint, GitBranch, RefreshCw, Search, ShieldCheck, Sparkles } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

type Tier = "SEMANTIC" | "PROCEDURAL" | "EPISODIC";
type Snapshot = { status: string; version: string; auth_enabled: boolean; identity: { tenant_id: string; owner_id: string; session_id: string }; counts: Record<Tier, number>; total_items: number; recent_items: Array<{ id: string; tier: Tier; scope: string; content: string; provenance: string; created_at: string }> };
type Assembly = { items: Array<{ id: string; tier: Tier; scope: string; content: string }>; excluded_items: Array<{ id: string; reason: string }>; tokens_used: number; candidates_truncated: number };

const demoSnapshot: Snapshot = {
  status: "demo signal", version: "0.2.0", auth_enabled: true,
  identity: { tenant_id: "acme-labs", owner_id: "maya", session_id: "research-42" },
  counts: { SEMANTIC: 128, PROCEDURAL: 34, EPISODIC: 76 }, total_items: 238,
  recent_items: [
    { id: "sem-product-brief", tier: "SEMANTIC", scope: "TENANT", content: "North-star metric is successful context reuse per agent run.", provenance: "product-notes.md", created_at: new Date(Date.now() - 62000).toISOString() },
    { id: "proc-eval-17", tier: "PROCEDURAL", scope: "SESSION", content: "Compared retrieval at budgets 200, 400, and 800 tokens.", provenance: "eval-agent", created_at: new Date(Date.now() - 242000).toISOString() },
    { id: "epi-user-pref", tier: "EPISODIC", scope: "USER", content: "Maya prefers concise results with source provenance attached.", provenance: "assistant", created_at: new Date(Date.now() - 541000).toISOString() },
    { id: "sem-policy", tier: "SEMANTIC", scope: "GLOBAL", content: "Never surface episodic memory across tenant boundaries.", provenance: "policy-engine", created_at: new Date(Date.now() - 1161000).toISOString() },
  ],
};
const tiers = [
  { key: "SEMANTIC" as Tier, label: "Semantic", note: "Durable facts", icon: BookOpen },
  { key: "PROCEDURAL" as Tier, label: "Procedural", note: "Task knowledge", icon: GitBranch },
  { key: "EPISODIC" as Tier, label: "Episodic", note: "Scoped events", icon: Clock3 },
];
function ago(value: string) { const seconds = Math.max(1, Math.round((Date.now() - new Date(value).getTime()) / 1000)); if (seconds < 60) return `${seconds}s ago`; if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`; return `${Math.floor(seconds / 3600)}h ago`; }

export default function Dashboard() {
  const [snapshot, setSnapshot] = useState<Snapshot>(demoSnapshot);
  const [live, setLive] = useState(false); const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("What should the research agent remember about Maya?");
  const [budget, setBudget] = useState(400); const [assembly, setAssembly] = useState<Assembly | null>(null); const [assembling, setAssembling] = useState(false);
  const refresh = useCallback(async () => { setLoading(true); try { const response = await fetch("/trilith/v1/dashboard", { cache: "no-store" }); if (!response.ok) throw new Error(); setSnapshot(await response.json()); setLive(true); } catch { setSnapshot(demoSnapshot); setLive(false); } finally { setLoading(false); } }, []);
  useEffect(() => { void refresh(); }, [refresh]);
  async function assemble(event: FormEvent) { event.preventDefault(); setAssembling(true); try { const response = await fetch("/trilith/v1/assemble", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ task: query, budget }) }); if (!response.ok) throw new Error(); setAssembly(await response.json()); } catch { setAssembly({ items: demoSnapshot.recent_items.slice(0, 3).map(({ id, tier, scope, content }) => ({ id, tier, scope, content })), excluded_items: [{ id: "proc-eval-17", reason: "privacy: session scope mismatch" }], tokens_used: Math.min(budget, 173), candidates_truncated: 0 }); } finally { setAssembling(false); } }
  const maxCount = useMemo(() => Math.max(...Object.values(snapshot.counts), 1), [snapshot]);

  return <main>
    <header className="topbar"><div className="brand"><span className="brand-mark"><span /><span /><span /></span><strong>TRILITH</strong><em>OBSERVATORY</em></div><div className="top-actions"><span className={`signal ${live ? "is-live" : ""}`}><i />{live ? "Core connected" : "Demo telemetry"}</span><button className="icon-button" onClick={refresh} aria-label="Refresh dashboard"><RefreshCw className={loading ? "spin" : ""} size={17} /></button><div className="avatar">MK</div></div></header>
    <section className="hero reveal"><div><p className="eyebrow">Context operations / {snapshot.identity.tenant_id}</p><h1>See what your agents<br /><span>carry forward.</span></h1></div><div className="hero-aside"><p>Trilith keeps context useful, scoped, and small. This is the live path from stored memory to the next prompt.</p><div className="identity"><Fingerprint size={16} /><span>{snapshot.identity.owner_id || "all owners"}</span><b>/</b><span>{snapshot.identity.session_id || "all sessions"}</span></div></div></section>
    <section className="metrics reveal delay-1"><article className="total-card"><div className="card-label"><Database size={15} /> Context inventory</div><div className="big-number">{snapshot.total_items.toLocaleString()}</div><div className="metric-foot"><span>visible items</span><span className="healthy"><CircleCheck size={13} /> governed</span></div></article>{tiers.map(({ key, label, note, icon: Icon }, index) => <article className={`tier-card tier-${index}`} key={key}><div className="tier-head"><span className="tier-icon"><Icon size={17} /></span><span>{String(index + 1).padStart(2, "0")}</span></div><strong>{snapshot.counts[key]}</strong><h2>{label}</h2><p>{note}</p><div className="bar"><i style={{ width: `${Math.max(8, snapshot.counts[key] / maxCount * 100)}%` }} /></div></article>)}</section>
    <section className="workspace reveal delay-2"><div className="activity-panel"><div className="section-heading"><div><p className="eyebrow">Memory stream</p><h2>Recent context</h2></div><span>{snapshot.recent_items.length} latest</span></div><div className="activity-list">{snapshot.recent_items.map(item => <article className="activity-row" key={item.id}><span className={`tier-dot ${item.tier.toLowerCase()}`} /><div className="activity-copy"><div><span>{item.tier}</span><b>·</b><span>{item.scope}</span></div><p>{item.content}</p><small>{item.provenance || "direct write"} · {ago(item.created_at)}</small></div><ArrowUpRight size={16} /></article>)}</div></div>
      <aside className="system-panel"><div className="section-heading"><div><p className="eyebrow">Core vitals</p><h2>System</h2></div><Activity size={19} /></div><div className="core-orbit"><div className="orbit orbit-a" /><div className="orbit orbit-b" /><div className="core"><Sparkles size={22} /><span>GOVERNOR</span></div></div><dl><div><dt>Runtime</dt><dd>{snapshot.status}</dd></div><div><dt>Privacy boundary</dt><dd>{snapshot.identity.tenant_id}</dd></div><div><dt>Authentication</dt><dd>{snapshot.auth_enabled ? "enforced" : "open / local"}</dd></div><div><dt>Core version</dt><dd>v{snapshot.version}</dd></div></dl><div className="guardrail"><ShieldCheck size={18} /><div><b>Policy engine active</b><span>Scope checked before ranking</span></div></div></aside></section>
    <section className="workbench reveal delay-3"><div className="workbench-copy"><p className="eyebrow">Assembly workbench</p><h2>Ask the memory.</h2><p>Run a task through Trilith’s governor and inspect exactly what earns a place in the context window.</p></div><form onSubmit={assemble}><label htmlFor="task">Task description</label><div className="query-box"><Search size={19} /><input id="task" value={query} onChange={event => setQuery(event.target.value)} /><button disabled={assembling || !query.trim()}>{assembling ? "Ranking…" : "Assemble"}<ArrowUpRight size={16} /></button></div><div className="budget-row"><span>Token budget</span><input type="range" min="100" max="1200" step="50" value={budget} onChange={event => setBudget(Number(event.target.value))} /><output>{budget}</output></div></form>{assembly && <div className="assembly-result"><div className="result-stat"><Braces size={18} /><div><strong>{assembly.tokens_used}</strong><span>tokens used</span></div></div><div className="result-stat"><CircleCheck size={18} /><div><strong>{assembly.items.length}</strong><span>items selected</span></div></div><div className="result-stat muted"><ShieldCheck size={18} /><div><strong>{assembly.excluded_items.length}</strong><span>policy exclusions</span></div></div><div className="selected-items">{assembly.items.map(item => <span key={item.id}><i className={item.tier.toLowerCase()} />{item.id}</span>)}</div></div>}</section>
    <footer><span>TRILITH / CONTEXT INFRASTRUCTURE</span><span>REST :8080 <i /> gRPC :50051</span></footer>
  </main>;
}
