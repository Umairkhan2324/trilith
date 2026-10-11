"use client";

import { AlertTriangle, Ban, Coins, Scale, Sparkles } from "lucide-react";
import { useState } from "react";
import { pluralize, truncate } from "@/lib/format";
import type { Assembly, ExclusionKind } from "@/lib/types";

/**
 * The three reasons an item can miss the prompt, worst-understood first.
 *
 * Collapsing them into one "excluded" list hides the only thing that makes the
 * list actionable: a policy refusal is a boundary, a relevance drop is the
 * ranker's judgement, and a budget drop is just arithmetic. Each is fixed a
 * different way.
 */
const EXCLUSION_GROUPS: { kind: ExclusionKind; title: string; note: string }[] = [
  {
    kind: "policy",
    title: "Refused by policy",
    note: "This identity may not receive them, so their content is not shown here.",
  },
  {
    kind: "relevance",
    title: "Below the relevance floor",
    note: "The ranker found no evidence these match the task. Widening the budget will not admit them.",
  },
  {
    kind: "budget",
    title: "Out of budget",
    note: "Relevant enough to admit, but the budget was already spent.",
  },
];

/**
 * Run a task through the governor and show the whole decision.
 *
 * The budget meter is the point: each included item is a segment as wide as it
 * is expensive, so "what fits" stops being an abstraction. Everything that did
 * not fit is listed underneath with the reason the core gave.
 */
export function Workbench({
  assembly,
  busy,
  onAssemble,
  onPick,
}: {
  assembly: Assembly | null;
  busy: boolean;
  onAssemble: (task: string, budget: number) => void;
  onPick: (id: string) => void;
}) {
  const [task, setTask] = useState("");
  const [budget, setBudget] = useState(400);

  const used = assembly?.tokens_used ?? 0;
  const cap = assembly?.budget || budget;

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (task.trim()) onAssemble(task.trim(), budget);
  }

  return (
    <section className="workbench">
      <div className="workbench-head">
        <p className="eyebrow">Assembly workbench</p>
        <h2>Ask the memory.</h2>
        <p className="workbench-blurb">
          Rank this tenant&apos;s context against a task, fill the budget, and read back exactly what
          earned a place — and what did not.
        </p>
      </div>

      <form onSubmit={submit} className="workbench-form">
        <label className="field">
          <span>Task</span>
          <textarea
            value={task}
            rows={3}
            placeholder="What should the agent remember for this step?"
            onChange={(event) => setTask(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) submit(event);
            }}
          />
        </label>

        <div className="budget-row">
          <span>Token budget</span>
          <input
            type="range"
            min={50}
            max={2000}
            step={50}
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
          />
          <output>{budget}</output>
          <button type="submit" className="primary-button" disabled={busy || !task.trim()}>
            <Sparkles size={14} /> {busy ? "Ranking…" : "Assemble"}
          </button>
        </div>
      </form>

      {assembly ? (
        <div className="assembly">
          <div className="budget-meter" title={`${used} of ${cap} tokens used`}>
            {assembly.items.map((item) => (
              <span
                key={item.id}
                className={`segment ${item.tier.toLowerCase()}`}
                style={{ width: `${Math.min(100, (item.tokens / Math.max(cap, 1)) * 100)}%` }}
                title={`${item.id} · ${item.tokens} tokens`}
              />
            ))}
            <span className="segment segment-free" />
          </div>

          <div className="assembly-stats">
            <span>
              <Coins size={13} /> <strong>{used}</strong> / {cap} tokens
            </span>
            <span>
              <Scale size={13} /> <strong>{assembly.items.length}</strong> included
            </span>
            <span className="muted">
              <Ban size={13} /> <strong>{assembly.excluded_items.length}</strong> excluded
            </span>
            {assembly.candidates_truncated > 0 ? (
              <span className="warn">
                <AlertTriangle size={13} /> {assembly.candidates_truncated} candidates never
                considered (pre-rank cap)
              </span>
            ) : null}
          </div>

          <div className="assembly-columns">
            <div>
              <h3>Included</h3>
              {assembly.items.length === 0 ? (
                <p className="empty">Nothing was admitted for this task.</p>
              ) : (
                <ol className="assembly-list">
                  {assembly.items.map((item, index) => (
                    <li key={item.id}>
                      <button type="button" onClick={() => onPick(item.id)}>
                        <span className="rank">{index + 1}</span>
                        <span className="assembly-body">
                          <span className="item-meta">
                            <code>{item.id}</code>
                            <span className={`pill pill-${item.tier.toLowerCase()}`}>{item.tier}</span>
                            <span className="pill pill-quiet">{item.tokens} tok</span>
                          </span>
                          <p>{truncate(item.content, 120)}</p>
                        </span>
                      </button>
                    </li>
                  ))}
                </ol>
              )}
            </div>

            <div>
              <h3>Excluded</h3>
              {assembly.excluded_items.length === 0 ? (
                <p className="empty">Nothing was dropped: everything visible was relevant and fit.</p>
              ) : null}

              {EXCLUSION_GROUPS.map((group) => {
                const rows = assembly.excluded_items.filter((item) => item.kind === group.kind);
                if (rows.length === 0) return null;
                return (
                  <div className="excluded-group" key={group.kind}>
                    <h4>
                      {group.title} · {pluralize(rows.length, "item")}
                    </h4>
                    <p className="group-note">{group.note}</p>
                    <ul className="assembly-list">
                      {rows.map((item) => (
                        <li key={item.id}>
                          <button type="button" onClick={() => onPick(item.id)}>
                            <span className="assembly-body">
                              <span className="item-meta">
                                <code>{item.id}</code>
                                <span className="pill pill-quiet">
                                  {group.kind === "policy" ? item.scope : `${item.tokens} tok`}
                                </span>
                              </span>
                              {item.content ? <p>{truncate(item.content, 110)}</p> : null}
                              {/* "Exceeded token budget" only repeats the heading. */}
                              {group.kind === "budget" ? null : (
                                <p className="reason">{item.reason}</p>
                              )}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      ) : (
        <p className="empty workbench-empty">
          Run a task to see the governor&apos;s decision.
        </p>
      )}
    </section>
  );
}
