"use client";

import { KeyRound, RotateCcw, ShieldCheck, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { EMPTY_SESSION } from "@/lib/useSession";
import type { Session, Snapshot } from "@/lib/types";

/**
 * Who the console is pretending to be.
 *
 * This is the most useful control on the page: change the owner and the same
 * store answers differently, which is Trilith's isolation model made visible
 * rather than described.
 */
export function IdentityPanel({
  session,
  snapshot,
  tenants,
  onApply,
  onClose,
}: {
  session: Session;
  snapshot: Snapshot | null;
  tenants: string[];
  onApply: (next: Partial<Session>) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Session>(session);

  useEffect(() => setDraft(session), [session]);

  const authEnabled = snapshot?.auth_enabled ?? false;

  function apply(event: React.FormEvent) {
    event.preventDefault();
    onApply(draft);
    onClose();
  }

  return (
    <form className="identity-panel" onSubmit={apply}>
      <div className="identity-grid">
        <label>
          <span>Tenant</span>
          <input
            value={draft.tenant_id}
            onChange={(event) => setDraft({ ...draft, tenant_id: event.target.value })}
            placeholder="default"
            disabled={authEnabled}
            list="known-tenants"
          />
          <datalist id="known-tenants">
            {tenants.map((tenant) => (
              <option key={tenant} value={tenant} />
            ))}
          </datalist>
        </label>

        <label>
          <span>Owner</span>
          <input
            value={draft.owner_id}
            onChange={(event) => setDraft({ ...draft, owner_id: event.target.value })}
            placeholder="all owners"
          />
        </label>

        <label>
          <span>Session</span>
          <input
            value={draft.session_id}
            onChange={(event) => setDraft({ ...draft, session_id: event.target.value })}
            placeholder="all sessions"
          />
        </label>

        <label>
          <span>
            <KeyRound size={11} /> API key
          </span>
          <input
            type="password"
            value={draft.apiKey}
            onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
            placeholder="tri_…"
            autoComplete="off"
          />
        </label>
      </div>

      <div className="identity-foot">
        <p>
          {authEnabled ? (
            <>
              <ShieldCheck size={12} /> Auth is enforced: the key decides the tenant, and the field
              above is ignored. Owner and session still narrow what you see inside it.
            </>
          ) : (
            <>
              <Users size={12} /> Auth is off, so these fields are taken at face value — switch owner
              to see the same store answer a different caller. The key is kept in this browser only.
            </>
          )}
        </p>
        <div className="identity-actions">
          <button type="button" className="ghost-button" onClick={() => setDraft(EMPTY_SESSION)}>
            <RotateCcw size={13} /> Clear
          </button>
          <button type="submit" className="primary-button">
            Apply identity
          </button>
        </div>
      </div>
    </form>
  );
}
