"use client";

import { EyeOff, Plus, Search, X } from "lucide-react";
import { forwardRef } from "react";
import { expiryLabel, relativeTime, truncate } from "@/lib/format";
import { SCOPES, TIERS, type Item, type ItemsPage, type Scope, type Tier } from "@/lib/types";

export type Filters = { tier: Tier | ""; scope: Scope | ""; q: string; offset: number };

/**
 * The stored context, searchable and selectable.
 *
 * Rows the current identity could not actually receive are kept in the list
 * and marked, because "it is in the store but the policy will not hand it to
 * you" is the state most worth being able to see.
 */
export const Explorer = forwardRef<HTMLInputElement, {
  page: ItemsPage | null;
  filters: Filters;
  loading: boolean;
  selectedId: string | null;
  onFilters: (next: Partial<Filters>) => void;
  onSelect: (item: Item) => void;
  onCompose: () => void;
}>(function Explorer({ page, filters, loading, selectedId, onFilters, onSelect, onCompose }, ref) {
  const items = page?.items ?? [];
  const total = page?.total ?? 0;
  const limit = page?.limit ?? 50;
  const from = total === 0 ? 0 : filters.offset + 1;
  const to = Math.min(filters.offset + items.length, total);

  return (
    <section className="explorer panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Stored context</p>
          <h2>Explorer</h2>
        </div>
        <button type="button" className="primary-button" onClick={onCompose}>
          <Plus size={14} /> New item
        </button>
      </div>

      <div className="filter-row">
        <div className="search-field">
          <Search size={15} />
          <input
            ref={ref}
            value={filters.q}
            placeholder="Search content, id, provenance, sub-task…   (/)"
            onChange={(event) => onFilters({ q: event.target.value, offset: 0 })}
          />
          {filters.q ? (
            <button type="button" onClick={() => onFilters({ q: "", offset: 0 })} aria-label="Clear search">
              <X size={13} />
            </button>
          ) : null}
        </div>

        <select
          value={filters.tier}
          onChange={(event) => onFilters({ tier: event.target.value as Tier | "", offset: 0 })}
          aria-label="Filter by tier"
        >
          <option value="">All tiers</option>
          {TIERS.map((tier) => (
            <option key={tier} value={tier}>
              {tier}
            </option>
          ))}
        </select>

        <select
          value={filters.scope}
          onChange={(event) => onFilters({ scope: event.target.value as Scope | "", offset: 0 })}
          aria-label="Filter by scope"
        >
          <option value="">All scopes</option>
          {SCOPES.map((scope) => (
            <option key={scope} value={scope}>
              {scope}
            </option>
          ))}
        </select>
      </div>

      <div className={`item-list ${loading ? "is-loading" : ""}`}>
        {items.length === 0 && !loading ? (
          <p className="empty">
            {filters.q || filters.tier || filters.scope
              ? "Nothing matches these filters."
              : "No context stored for this identity yet."}
          </p>
        ) : null}

        {items.map((item) => {
          const expiry = expiryLabel(item.expires_at);
          return (
            <article
              key={item.id}
              className={`item-row ${selectedId === item.id ? "is-selected" : ""} ${
                item.visible ? "" : "is-hidden-item"
              }`}
              onClick={() => onSelect(item)}
              role="button"
              tabIndex={0}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  onSelect(item);
                }
              }}
            >
              <span className={`tier-dot ${item.tier.toLowerCase()}`} aria-hidden />
              <div className="item-body">
                <div className="item-meta">
                  <code>{item.id}</code>
                  <span className="pill">{item.tier}</span>
                  <span className="pill pill-quiet">{item.scope}</span>
                  {item.subtask_id ? <span className="pill pill-quiet">↯ {item.subtask_id}</span> : null}
                  {expiry ? <span className="pill pill-warn">{expiry}</span> : null}
                  {item.visible ? null : (
                    <span className="pill pill-blocked" title={item.visibility_reason}>
                      <EyeOff size={10} /> not visible
                    </span>
                  )}
                </div>
                <p>{truncate(item.content)}</p>
                <small>
                  {item.provenance || "direct write"} · {relativeTime(item.created_at)} ·{" "}
                  {item.tokens} tok
                  {item.owner_id ? ` · owner ${item.owner_id}` : ""}
                  {item.session_id ? ` · session ${item.session_id}` : ""}
                </small>
                {item.visible ? null : <small className="blocked-reason">{item.visibility_reason}</small>}
              </div>
            </article>
          );
        })}
      </div>

      <div className="pager">
        <span>
          {total === 0 ? "no items" : `${from}–${to} of ${total}`}
        </span>
        <div>
          <button
            type="button"
            className="ghost-button"
            disabled={filters.offset === 0}
            onClick={() => onFilters({ offset: Math.max(0, filters.offset - limit) })}
          >
            Previous
          </button>
          <button
            type="button"
            className="ghost-button"
            disabled={to >= total}
            onClick={() => onFilters({ offset: filters.offset + limit })}
          >
            Next
          </button>
        </div>
      </div>
    </section>
  );
});
