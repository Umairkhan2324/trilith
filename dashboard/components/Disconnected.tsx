"use client";

import { KeyRound, PlugZap, RefreshCw } from "lucide-react";
import type { Connection } from "@/lib/connection";

/**
 * What the console shows when it has nothing real to show.
 *
 * It deliberately does not invent data. A dashboard that renders plausible
 * numbers while disconnected teaches an operator to distrust every number on
 * it, which is worse than an empty screen.
 */
export function Disconnected({
  connection,
  detail,
  onRetry,
  onOpenIdentity,
}: {
  connection: Connection;
  detail: string;
  onRetry: () => void;
  onOpenIdentity: () => void;
}) {
  const unauthorized = connection === "unauthorized";

  return (
    <section className="disconnected">
      <span className="disconnected-icon">{unauthorized ? <KeyRound size={22} /> : <PlugZap size={22} />}</span>
      <h2>{unauthorized ? "This instance wants a key" : "Trilith Core is not answering"}</h2>

      {unauthorized ? (
        <>
          <p>
            A key exists on this database, so auth is enforced and every request needs one. Paste it
            into the identity panel — it stays in this browser.
          </p>
          <div className="disconnected-actions">
            <button type="button" className="primary-button" onClick={onOpenIdentity}>
              Enter API key
            </button>
            <button type="button" className="ghost-button" onClick={onRetry}>
              <RefreshCw size={13} /> Retry
            </button>
          </div>
          <p className="disconnected-hint">
            Mint one with <code>trilith key create --tenant &lt;name&gt;</code>. It is shown once.
          </p>
        </>
      ) : (
        <>
          <p>
            The console proxies <code>/trilith/*</code> to the REST gateway. Start the core, then
            retry:
          </p>
          <pre>trilith serve --host 127.0.0.1 --port 8080 --grpc-port 50051</pre>
          <div className="disconnected-actions">
            <button type="button" className="primary-button" onClick={onRetry}>
              <RefreshCw size={13} /> Retry
            </button>
          </div>
          <p className="disconnected-hint">
            Pointing somewhere else? Set <code>TRILITH_API_URL</code> before <code>npm run dev</code>.
            {detail ? ` (${detail})` : ""}
          </p>
        </>
      )}
    </section>
  );
}
