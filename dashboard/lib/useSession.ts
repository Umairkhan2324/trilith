"use client";

import { useCallback, useEffect, useState } from "react";
import type { Session } from "./types";

const STORAGE_KEY = "trilith.session";

export const EMPTY_SESSION: Session = {
  tenant_id: "",
  owner_id: "",
  session_id: "",
  apiKey: "",
};

/**
 * The identity this console is acting as, persisted per browser.
 *
 * The API key lives in localStorage rather than in the bundle: a key baked
 * into NEXT_PUBLIC_* would ship to everyone who loads the page. Here it stays
 * on the operator's machine and travels only to their own core.
 */
export function useSession(): [Session, (next: Partial<Session>) => void, boolean] {
  const [session, setSession] = useState<Session>(EMPTY_SESSION);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) setSession({ ...EMPTY_SESSION, ...JSON.parse(stored) });
    } catch {
      // A corrupt or blocked store is not worth failing the console over.
    }
    setReady(true);
  }, []);

  const update = useCallback((next: Partial<Session>) => {
    setSession((current) => {
      const merged = { ...current, ...next };
      try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(merged));
      } catch {
        // Ignore: the session still applies for this page load.
      }
      return merged;
    });
  }, []);

  return [session, update, ready];
}
