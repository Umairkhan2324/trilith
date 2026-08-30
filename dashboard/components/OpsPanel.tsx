"use client";

import { FoldVertical, ShieldCheck, Timer, Wind } from "lucide-react";
import { useEffect, useState } from "react";
import { ConfirmButton } from "./ConfirmButton";
import { pluralize } from "@/lib/format";
import { SCOPES, type Scope, type Snapshot, type Subtask } from "@/lib/types";

/**
 * The three pipeline operations that are not writes, plus what the core says
 * about itself.
 *
 * `fold` and `forget` are destructive and physical, so both are two-step and
 * both name exactly what they will touch before they touch it.
 */
export function OpsPanel({
  snapshot,
  subtasks,
  busy,
  onFold,
  onForget,
  onPurge,
}: {
  snapshot: Snapshot | null;
  subtasks: Subtask[];
  busy: boolean;
  onFold: (subtaskId: string) => void;
  onForget: (scope: Scope) => void;
  onPurge: () => void;
}) {
  const [subtask, setSubtask] = useState("");
  const [scope, setScope] = useState<Scope>("SESSION");

  useEffect(() => {
    // Keep the selection pointed at something that still exists after a fold.
    if (subtasks.length === 0) setSubtask("");
    else if (!subtasks.some((entry) => entry.subtask_id === subtask)) {
      setSubtask(subtasks[0].subtask_id);
    }
  }, [subtasks, subtask]);

  const selected = subtasks.find((entry) => entry.subtask_id === subtask);

  return (
    <aside className="ops panel">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Core vitals</p>
          <h2>Operations</h2>
        </div>
        <ShieldCheck size={17} />
      </div>

      <dl className="vitals">
        <div>
          <dt>Runtime</dt>
          <dd>{snapshot?.status ?? "unknown"}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>v{snapshot?.version ?? "—"}</dd>
        </div>
        <div>
          <dt>Auth</dt>
          <dd>{snapshot?.auth_enabled ? "enforced" : "open / local"}</dd>
        </div>
        <div>
          <dt>Tenant boundary</dt>
          <dd>{snapshot?.identity.tenant_id ?? "—"}</dd>
        </div>
      </dl>

      <div className="op">
        <label className="field">
          <span>
            <FoldVertical size={11} /> Fold a sub-task
          </span>
          <select value={subtask} onChange={(event) => setSubtask(event.target.value)}>
            {subtasks.length === 0 ? <option value="">no sub-tasks with steps</option> : null}
            {subtasks.map((entry) => (
              <option key={entry.subtask_id} value={entry.subtask_id}>
                {entry.subtask_id} · {pluralize(entry.steps, "step")}
              </option>
            ))}
          </select>
        </label>
        <ConfirmButton
          className="ghost-button wide"
          label={selected ? `Fold ${pluralize(selected.steps, "step")} into one` : "Fold"}
          confirmLabel="Replace those steps?"
          disabled={busy || !subtask}
          onConfirm={() => onFold(subtask)}
        />
      </div>

      <div className="op">
        <label className="field">
          <span>
            <Wind size={11} /> Forget a scope
          </span>
          <select value={scope} onChange={(event) => setScope(event.target.value as Scope)}>
            {SCOPES.map((entry) => (
              <option key={entry} value={entry}>
                {entry}
              </option>
            ))}
          </select>
          <small>
            Deletes every {scope} item across all three tiers, inside this tenant. USER and SESSION
            are further narrowed to the identity above.
          </small>
        </label>
        <ConfirmButton
          className="danger-button wide"
          label={`Forget ${scope}`}
          confirmLabel="Erase permanently?"
          disabled={busy}
          onConfirm={() => onForget(scope)}
        />
      </div>

      <div className="op">
        <button type="button" className="ghost-button wide" onClick={onPurge} disabled={busy}>
          <Timer size={13} /> Purge expired items
        </button>
        <small className="op-note">
          Expired items are already invisible to assembly; purging reclaims the rows.
        </small>
      </div>
    </aside>
  );
}
