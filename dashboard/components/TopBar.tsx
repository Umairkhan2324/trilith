"use client";

import { Fingerprint, Pause, Play, RefreshCw } from "lucide-react";
import type { Connection } from "@/lib/connection";
import type { Session, Snapshot } from "@/lib/types";

const STATUS_TEXT: Record<Connection, string> = {
  connecting: "Connecting",
  online: "Core connected",
  offline: "Core unreachable",
  unauthorized: "Key required",
};

export function TopBar({
  connection,
  snapshot,
  session,
  live,
  refreshing,
  identityOpen,
  onToggleLive,
  onRefresh,
  onToggleIdentity,
}: {
  connection: Connection;
  snapshot: Snapshot | null;
  session: Session;
  live: boolean;
  refreshing: boolean;
  identityOpen: boolean;
  onToggleLive: () => void;
  onRefresh: () => void;
  onToggleIdentity: () => void;
}) {
  const tenant = snapshot?.identity.tenant_id ?? session.tenant_id ?? "";
  const owner = snapshot?.identity.owner_id || "all owners";
  const sessionId = snapshot?.identity.session_id || "all sessions";

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" aria-hidden>
          <span />
          <span />
          <span />
        </span>
        <strong>TRILITH</strong>
        <em>OBSERVATORY</em>
      </div>

      <div className="top-actions">
        <button
          type="button"
          className={`identity-chip ${identityOpen ? "is-open" : ""}`}
          onClick={onToggleIdentity}
          title="Change the identity this console acts as"
        >
          <Fingerprint size={14} />
          <span className="identity-chip-tenant">{tenant || "no tenant"}</span>
          <span className="identity-chip-rest">
            {owner} / {sessionId}
          </span>
          {snapshot?.auth_enabled ? <b className="pinned">key-pinned</b> : null}
        </button>

        <span className={`signal signal-${connection}`}>
          <i />
          {STATUS_TEXT[connection]}
        </span>

        <button
          type="button"
          className={`icon-button ${live ? "is-active" : ""}`}
          onClick={onToggleLive}
          aria-label={live ? "Pause live updates" : "Resume live updates"}
          title={live ? "Pause live updates" : "Resume live updates"}
        >
          {live ? <Pause size={15} /> : <Play size={15} />}
        </button>

        <button
          type="button"
          className="icon-button"
          onClick={onRefresh}
          aria-label="Refresh now"
          title="Refresh now"
        >
          <RefreshCw size={15} className={refreshing ? "spin" : ""} />
        </button>
      </div>
    </header>
  );
}
