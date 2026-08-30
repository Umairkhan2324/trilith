"use client";

import { EyeOff, Save, Trash2, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ConfirmButton } from "./ConfirmButton";
import { absoluteTime, expiryLabel, relativeTime, scopeNote } from "@/lib/format";
import { SCOPES, TIERS, type Draft, type Item, type Scope, type Tier } from "@/lib/types";

export type InspectorMode = "empty" | "edit" | "create";

const BLANK: Draft = {
  id: "",
  tier: "SEMANTIC",
  scope: "TENANT",
  content: "",
  provenance: "",
  owner_id: "",
  session_id: "",
  subtask_id: "",
  ttl_seconds: "",
};

function draftFrom(item: Item): Draft {
  return {
    id: item.id,
    tier: item.tier,
    scope: item.scope === "SCOPE_UNSPECIFIED" ? "TENANT" : item.scope,
    content: item.content,
    provenance: item.provenance,
    owner_id: item.owner_id,
    session_id: item.session_id,
    subtask_id: item.subtask_id,
    ttl_seconds: "",
  };
}

/**
 * Read, edit, or write one item.
 *
 * An edit sends only the fields that actually changed, so an operator fixing
 * a typo cannot accidentally re-scope a row or drop its sub-task on the way
 * past.
 */
export function Inspector({
  mode,
  item,
  busy,
  onCreate,
  onSave,
  onDelete,
  onClose,
}: {
  mode: InspectorMode;
  item: Item | null;
  busy: boolean;
  onCreate: (draft: Draft) => void;
  onSave: (id: string, changes: Partial<Draft>) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(BLANK);

  useEffect(() => {
    if (mode === "create") setDraft(BLANK);
    else if (item) setDraft(draftFrom(item));
  }, [mode, item]);

  const changed = useMemo(() => {
    if (mode !== "edit" || !item) return [];
    const original = draftFrom(item);
    const keys = Object.keys(original) as (keyof Draft)[];
    const diff = keys.filter((key) => key !== "id" && key !== "ttl_seconds" && draft[key] !== original[key]);
    if (draft.ttl_seconds.trim() !== "") diff.push("ttl_seconds");
    return diff;
  }, [mode, item, draft]);

  if (mode === "empty") {
    return (
      <aside className="inspector panel is-empty">
        <p className="eyebrow">Inspector</p>
        <p className="empty">
          Select an item to read it, edit it in place, or delete it. Nothing here is a preview —
          every change is written straight to the store.
        </p>
      </aside>
    );
  }

  const creating = mode === "create";

  function submit(event: React.FormEvent) {
    event.preventDefault();
    if (creating) {
      onCreate(draft);
      return;
    }
    if (!item || changed.length === 0) return;
    const changes: Partial<Draft> = {};
    // Both sides are the same shape keyed the same way, but TypeScript cannot
    // correlate the index across a union of value types, so assert it once.
    for (const key of changed) (changes as Record<string, string>)[key] = draft[key];
    onSave(item.id, changes);
  }

  return (
    <aside className="inspector panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">{creating ? "Compose" : "Inspector"}</p>
          <h2>{creating ? "New item" : "Edit item"}</h2>
        </div>
        <button type="button" className="icon-button" onClick={onClose} aria-label="Close inspector">
          <X size={15} />
        </button>
      </div>

      {!creating && item && !item.visible ? (
        <p className="blocked-banner">
          <EyeOff size={13} /> {item.visibility_reason}
        </p>
      ) : null}

      <form className="inspector-form" onSubmit={submit}>
        <label className="field">
          <span>Identifier</span>
          <input
            value={draft.id}
            onChange={(event) => setDraft({ ...draft, id: event.target.value })}
            disabled={!creating}
            placeholder="unique-id"
            required
          />
          {creating ? <small>Writing an existing id replaces that item.</small> : null}
        </label>

        <div className="field-pair">
          <label className="field">
            <span>Tier</span>
            <select
              value={draft.tier}
              onChange={(event) => setDraft({ ...draft, tier: event.target.value as Tier })}
            >
              {TIERS.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </select>
          </label>

          <label className="field">
            <span>Scope</span>
            <select
              value={draft.scope}
              onChange={(event) => setDraft({ ...draft, scope: event.target.value as Scope })}
            >
              {SCOPES.map((scope) => (
                <option key={scope} value={scope}>
                  {scope}
                </option>
              ))}
            </select>
            <small>{scopeNote[draft.scope]}</small>
          </label>
        </div>

        <label className="field">
          <span>Content</span>
          <textarea
            value={draft.content}
            rows={7}
            onChange={(event) => setDraft({ ...draft, content: event.target.value })}
            placeholder="What should the agent remember?"
            required
          />
        </label>

        <div className="field-pair">
          <label className="field">
            <span>Provenance</span>
            <input
              value={draft.provenance}
              onChange={(event) => setDraft({ ...draft, provenance: event.target.value })}
              placeholder="where it came from"
            />
          </label>
          <label className="field">
            <span>Sub-task</span>
            <input
              value={draft.subtask_id}
              onChange={(event) => setDraft({ ...draft, subtask_id: event.target.value })}
              placeholder="groups procedural steps"
            />
          </label>
        </div>

        <div className="field-pair">
          <label className="field">
            <span>Owner</span>
            <input
              value={draft.owner_id}
              onChange={(event) => setDraft({ ...draft, owner_id: event.target.value })}
              placeholder="for USER scope"
            />
          </label>
          <label className="field">
            <span>Session</span>
            <input
              value={draft.session_id}
              onChange={(event) => setDraft({ ...draft, session_id: event.target.value })}
              placeholder="for SESSION scope"
            />
          </label>
        </div>

        <label className="field">
          <span>{creating ? "Expires in (seconds)" : "Reset expiry to (seconds from now)"}</span>
          <input
            value={draft.ttl_seconds}
            inputMode="numeric"
            onChange={(event) => setDraft({ ...draft, ttl_seconds: event.target.value })}
            placeholder={creating ? "blank = never expires" : "blank = leave as is · 0 = never"}
          />
          {!creating && item?.expires_at ? (
            <small>
              currently {expiryLabel(item.expires_at)} · {absoluteTime(item.expires_at)}
            </small>
          ) : null}
        </label>

        {!creating && item ? (
          <dl className="facts">
            <div>
              <dt>Tenant</dt>
              <dd>{item.tenant_id}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd title={absoluteTime(item.created_at)}>{relativeTime(item.created_at)}</dd>
            </div>
            <div>
              <dt>Token cost</dt>
              <dd>{item.tokens}</dd>
            </div>
          </dl>
        ) : null}

        <div className="inspector-actions">
          {!creating && item ? (
            <ConfirmButton
              className="danger-button"
              label="Delete"
              confirmLabel="Delete for good?"
              icon={<Trash2 size={13} />}
              disabled={busy}
              onConfirm={() => onDelete(item.id)}
            />
          ) : (
            <span />
          )}
          <div className="inspector-submit">
            {!creating && changed.length > 0 ? (
              <span className="change-hint">{changed.join(", ")} changed</span>
            ) : null}
            <button
              type="submit"
              className="primary-button"
              disabled={busy || (!creating && changed.length === 0) || !draft.content.trim() || !draft.id.trim()}
            >
              <Save size={14} /> {creating ? "Write to store" : "Save changes"}
            </button>
          </div>
        </div>
      </form>
    </aside>
  );
}
