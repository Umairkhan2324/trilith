"use client";

import { AlertTriangle, Ban, Coins, Scale, Sparkles } from "lucide-react";
import { useState } from "react";
import { pluralize, truncate } from "@/lib/format";
import type { Assembly } from "@/lib/types";

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

  const budgetExcluded = assembly?.excluded_items.filter((item) => item.kind === "budget") ?? [];
  const policyExcluded = assembly?.excluded_items.filter((item) => item.kind === "policy") ?? [];
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
                <p className="empty">Everything visible fit inside the budget.</p>
              ) : null}

              {policyExcluded.length > 0 ? (
                <div className="excluded-group">
                  <h4>
                    Policy · {pluralize(policyExcluded.length, "item")}
                  </h4>
                  <ul className="assembly-list">
                    {policyExcluded.map((item) => (
                      <li key={item.id}>
                        <button type="button" onClick={() => onPick(item.id)}>
                          <span className="assembly-body">
                            <span className="item-meta">
                              <code>{item.id}</code>
                              <span className="pill pill-quiet">{item.scope}</span>
                            </span>
                            <p className="reason">{item.reason}</p>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {budgetExcluded.length > 0 ? (
                <div className="excluded-group">
                  <h4>Budget · {pluralize(budgetExcluded.length, "item")}</h4>
                  <ul className="assembly-list">
                    {budgetExcluded.map((item) => (
                      <li key={item.id}>
                        <button type="button" onClick={() => onPick(item.id)}>
                          <span className="assembly-body">
                            <span className="item-meta">
                              <code>{item.id}</code>
                              <span className="pill pill-quiet">{item.tokens} tok</span>
                            </span>
                            <p>{truncate(item.content, 100)}</p>
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
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
