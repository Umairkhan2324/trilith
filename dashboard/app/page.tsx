"use client";

import { Sprout } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { ActivityFeed } from "@/components/ActivityFeed";
import { Disconnected } from "@/components/Disconnected";
import { Explorer, type Filters } from "@/components/Explorer";
import { IdentityPanel } from "@/components/IdentityPanel";
import { Inspector, type InspectorMode } from "@/components/Inspector";
import { OpsPanel } from "@/components/OpsPanel";
import { TierStats } from "@/components/TierStats";
import { useToast } from "@/components/Toaster";
import { TopBar } from "@/components/TopBar";
import { Workbench } from "@/components/Workbench";
import { api } from "@/lib/api";
import { classify, describeError, type Connection } from "@/lib/connection";
import { SAMPLE_CONTEXT } from "@/lib/sample";
import { useSession } from "@/lib/useSession";
import type {
  Assembly,
  Draft,
  Item,
  ItemsPage,
  Scope,
  Snapshot,
  Subtask,
  Tier,
  TrilithEvent,
} from "@/lib/types";

const POLL_MS = 2000;
const FEED_LENGTH = 60;

export default function Observatory() {
  const [session, updateSession, sessionReady] = useSession();
  const toast = useToast();

  const [connection, setConnection] = useState<Connection>("connecting");
  const [detail, setDetail] = useState("");
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [page, setPage] = useState<ItemsPage | null>(null);
  const [subtasks, setSubtasks] = useState<Subtask[]>([]);
  const [tenants, setTenants] = useState<string[]>([]);
  const [events, setEvents] = useState<TrilithEvent[]>([]);
  const [assembly, setAssembly] = useState<Assembly | null>(null);

  const [filters, setFilters] = useState<Filters>({ tier: "", scope: "", q: "", offset: 0 });
  const [selected, setSelected] = useState<Item | null>(null);
  const [mode, setMode] = useState<InspectorMode>("empty");

  const [live, setLive] = useState(true);
  const [loadingItems, setLoadingItems] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [assembling, setAssembling] = useState(false);
  const [identityOpen, setIdentityOpen] = useState(false);

  // The event cursor and the live filters are read inside the polling loop,
  // which must not be re-created every keystroke.
  const cursor = useRef(0);
  const filtersRef = useRef(filters);
  filtersRef.current = filters;
  const searchRef = useRef<HTMLInputElement>(null);

  const onFailure = useCallback(
    (error: unknown) => {
      const kind = classify(error);
      if (kind) {
        setConnection(kind);
        setDetail(describeError(error));
      } else {
        toast("error", describeError(error));
      }
    },
    [toast],
  );

  const loadItems = useCallback(
    async (next: Filters) => {
      setLoadingItems(true);
      try {
        setPage(await api.items(session, next));
        setConnection("online");
      } catch (error) {
        onFailure(error);
      } finally {
        setLoadingItems(false);
      }
    },
    [session, onFailure],
  );

  const loadEvents = useCallback(async () => {
    const body = await api.events(session, cursor.current);
    cursor.current = body.latest_seq;
    if (body.events.length > 0) {
      setEvents((current) => [...body.events.slice().reverse(), ...current].slice(0, FEED_LENGTH));
    }
    return body.events.length;
  }, [session]);

  const refreshAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const [snap, subtaskBody, tenantBody] = await Promise.all([
        api.snapshot(session),
        api.subtasks(session),
        api.tenants(session),
      ]);
      setSnapshot(snap);
      setSubtasks(subtaskBody.subtasks);
      setTenants(tenantBody.tenants);
      setConnection("online");
      setDetail("");
      await Promise.all([loadItems(filtersRef.current), loadEvents()]);
    } catch (error) {
      onFailure(error);
    } finally {
      setRefreshing(false);
    }
  }, [session, loadItems, loadEvents, onFailure]);

  // A change of identity is a change of world: drop the feed cursor and the
  // selection rather than showing one tenant's rows under another's name.
  useEffect(() => {
    if (!sessionReady) return;
    cursor.current = 0;
    setEvents([]);
    setSelected(null);
    setMode("empty");
    setAssembly(null);
    void refreshAll();
    // refreshAll changes with the session, which is exactly when this should run.
  }, [sessionReady, refreshAll]);

  // Filters: debounced, because the search box types into a SQL LIKE.
  useEffect(() => {
    if (!sessionReady || connection === "offline" || connection === "unauthorized") return;
    const timer = window.setTimeout(() => void loadItems(filters), 220);
    return () => window.clearTimeout(timer);
  }, [filters, sessionReady, connection, loadItems]);

  // Live traffic. New events mean the store moved, so the counts and the list
  // are refetched too - including when the writer was someone else entirely.
  useEffect(() => {
    if (!live || !sessionReady || connection !== "online") return;
    const timer = window.setInterval(async () => {
      try {
        const arrived = await loadEvents();
        if (arrived > 0) {
          const [snap, subtaskBody] = await Promise.all([api.snapshot(session), api.subtasks(session)]);
          setSnapshot(snap);
          setSubtasks(subtaskBody.subtasks);
          await loadItems(filtersRef.current);
        }
      } catch (error) {
        onFailure(error);
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [live, sessionReady, connection, session, loadEvents, loadItems, onFailure]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      const typing = target && /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName);
      if (event.key === "/" && !typing) {
        event.preventDefault();
        searchRef.current?.focus();
      }
      if (event.key === "Escape") {
        setIdentityOpen(false);
        setMode("empty");
        setSelected(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  async function run(action: () => Promise<string>) {
    setBusy(true);
    try {
      toast("ok", await action());
      await refreshAll();
    } catch (error) {
      onFailure(error);
    } finally {
      setBusy(false);
    }
  }

  function create(draft: Draft) {
    void run(async () => {
      await api.write(session, draft);
      setMode("empty");
      return `Wrote ${draft.id}`;
    });
  }

  function save(id: string, changes: Partial<Draft>) {
    void run(async () => {
      const body = await api.patch(session, id, changes);
      if (body.item) setSelected(body.item);
      return body.changed.length ? `Updated ${id} (${body.changed.join(", ")})` : `${id} unchanged`;
    });
  }

  function remove(id: string) {
    void run(async () => {
      await api.remove(session, id);
      setSelected(null);
      setMode("empty");
      return `Deleted ${id}`;
    });
  }

  function fold(subtaskId: string) {
    void run(async () => {
      const body = await api.fold(session, subtaskId);
      if (!body.success) throw new Error(body.message);
      return `Folded ${body.folded_count} steps of ${subtaskId}`;
    });
  }

  function forget(scope: Scope) {
    void run(async () => {
      const body = await api.forget(session, scope);
      setSelected(null);
      setMode("empty");
      return `Forgot ${scope}: ${body.deleted_episodic_count} episodic items removed`;
    });
  }

  function purge() {
    void run(async () => {
      const body = await api.purgeExpired(session);
      return `Purged ${body.deleted_count} expired items`;
    });
  }

  function seed() {
    void run(async () => {
      for (const draft of SAMPLE_CONTEXT) await api.write(session, draft);
      return `Wrote ${SAMPLE_CONTEXT.length} sample items`;
    });
  }

  async function assemble(task: string, budget: number) {
    setAssembling(true);
    try {
      setAssembly(await api.assemble(session, task, budget));
    } catch (error) {
      onFailure(error);
    } finally {
      setAssembling(false);
    }
  }

  async function pick(id: string) {
    try {
      const item = await api.item(session, id);
      setSelected(item);
      setMode("edit");
    } catch (error) {
      toast("info", `${id} is not readable from this tenant`);
      void error;
    }
  }

  function selectItem(item: Item) {
    setSelected(item);
    setMode("edit");
  }

  const disconnected = connection === "offline" || connection === "unauthorized";
  const empty = connection === "online" && (snapshot?.total_items ?? 0) === 0;

  return (
    <main>
      <TopBar
        connection={connection}
        snapshot={snapshot}
        session={session}
        live={live}
        refreshing={refreshing}
        identityOpen={identityOpen}
        onToggleLive={() => setLive((value) => !value)}
        onRefresh={() => void refreshAll()}
        onToggleIdentity={() => setIdentityOpen((value) => !value)}
      />

      {identityOpen ? (
        <IdentityPanel
          session={session}
          snapshot={snapshot}
          tenants={tenants}
          onApply={updateSession}
          onClose={() => setIdentityOpen(false)}
        />
      ) : null}

      {disconnected ? (
        <Disconnected
          connection={connection}
          detail={detail}
          onRetry={() => void refreshAll()}
          onOpenIdentity={() => setIdentityOpen(true)}
        />
      ) : (
        <>
          <TierStats
            snapshot={snapshot}
            activeTier={filters.tier}
            onSelectTier={(tier: Tier | "") => setFilters({ ...filters, tier, offset: 0 })}
          />

          {empty ? (
            <div className="seed-banner">
              <div>
                <strong>This tenant has no context yet.</strong>
                <span>
                  Write a small set of real items — facts, a sub-task with steps, and a
                  session-scoped event — so there is something to rank, fold, and forget.
                </span>
              </div>
              <button type="button" className="primary-button" onClick={seed} disabled={busy}>
                <Sprout size={14} /> Write sample context
              </button>
            </div>
          ) : null}

          <div className="workspace">
            <Explorer
              ref={searchRef}
              page={page}
              filters={filters}
              loading={loadingItems}
              selectedId={selected?.id ?? null}
              onFilters={(next) => setFilters({ ...filters, ...next })}
              onSelect={selectItem}
              onCompose={() => {
                setSelected(null);
                setMode("create");
              }}
            />
            <Inspector
              mode={mode}
              item={selected}
              busy={busy}
              onCreate={create}
              onSave={save}
              onDelete={remove}
              onClose={() => {
                setMode("empty");
                setSelected(null);
              }}
            />
          </div>

          <Workbench assembly={assembly} busy={assembling} onAssemble={assemble} onPick={pick} />

          <div className="lower">
            <ActivityFeed events={events} live={live} />
            <OpsPanel
              snapshot={snapshot}
              subtasks={subtasks}
              busy={busy}
              onFold={fold}
              onForget={forget}
              onPurge={purge}
            />
          </div>
        </>
      )}

      <footer>
        <span>TRILITH / CONTEXT INFRASTRUCTURE</span>
        <span>
          REST :8080 <i /> gRPC :50051
        </span>
      </footer>
    </main>
  );
}
