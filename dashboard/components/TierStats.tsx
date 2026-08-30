"use client";

import { BookOpen, Clock3, Database, GitBranch } from "lucide-react";
import { tierLabel, tierNote } from "@/lib/format";
import { TIERS, type Snapshot, type Tier } from "@/lib/types";

const ICONS = { SEMANTIC: BookOpen, PROCEDURAL: GitBranch, EPISODIC: Clock3 };

/** Inventory, and the fastest way to filter the explorer down to one tier. */
export function TierStats({
  snapshot,
  activeTier,
  onSelectTier,
}: {
  snapshot: Snapshot | null;
  activeTier: Tier | "";
  onSelectTier: (tier: Tier | "") => void;
}) {
  const counts = snapshot?.counts;
  const total = snapshot?.total_items ?? 0;
  const max = Math.max(1, ...TIERS.map((tier) => counts?.[tier] ?? 0));

  return (
    <section className="metrics">
      <button
        type="button"
        className={`total-card ${activeTier === "" ? "is-active" : ""}`}
        onClick={() => onSelectTier("")}
      >
        <span className="card-label">
          <Database size={14} /> Context inventory
        </span>
        <span className="big-number">{total.toLocaleString()}</span>
        <span className="metric-foot">
          <span>visible to this identity</span>
          <span>{activeTier === "" ? "all tiers" : "show all"}</span>
        </span>
      </button>

      {TIERS.map((tier, index) => {
        const Icon = ICONS[tier];
        const count = counts?.[tier] ?? 0;
        const active = activeTier === tier;
        return (
          <button
            type="button"
            key={tier}
            className={`tier-card tier-${index} ${active ? "is-active" : ""}`}
            onClick={() => onSelectTier(active ? "" : tier)}
            title={`Filter the explorer to ${tierLabel[tier].toLowerCase()} items`}
          >
            <span className="tier-head">
              <span className="tier-icon">
                <Icon size={16} />
              </span>
              <span>{String(index + 1).padStart(2, "0")}</span>
            </span>
            <strong>{count}</strong>
            <span className="tier-name">{tierLabel[tier]}</span>
            <span className="tier-note">{tierNote[tier]}</span>
            <span className="bar">
              <i style={{ width: `${count === 0 ? 0 : Math.max(8, (count / max) * 100)}%` }} />
            </span>
          </button>
        );
      })}
    </section>
  );
}
