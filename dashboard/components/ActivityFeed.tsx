"use client";

import {
  Activity,
  FileEdit,
  FilePlus2,
  FoldVertical,
  Sparkles,
  Trash2,
  Wind,
} from "lucide-react";
import { relativeTime } from "@/lib/format";
import type { TrilithEvent } from "@/lib/types";

const ICONS: Record<string, typeof Activity> = {
  write: FilePlus2,
  update: FileEdit,
  delete: Trash2,
  assemble: Sparkles,
  fold: FoldVertical,
  forget: Wind,
  purge: Wind,
};

/**
 * Everything the core has done lately, whoever did it.
 *
 * The log is the instance's, not the browser's: an agent writing over gRPC
 * appears here next to an edit made in this tab. It is in-memory and bounded,
 * so it shows live traffic rather than history.
 */
export function ActivityFeed({ events, live }: { events: TrilithEvent[]; live: boolean }) {
  return (
    <section className="feed">
      <div className="panel-head">
        <div>
          <p className="eyebrow">Live traffic</p>
          <h2>Activity</h2>
        </div>
        <span className={`feed-state ${live ? "is-live" : ""}`}>{live ? "streaming" : "paused"}</span>
      </div>

      {events.length === 0 ? (
        <p className="empty">
          No operations yet. Anything this console, an agent, or the CLI does will appear here.
        </p>
      ) : (
        <ol className="feed-list">
          {events.map((event) => {
            const Icon = ICONS[event.kind] ?? Activity;
            return (
              <li key={event.seq} className={`feed-item feed-${event.kind}`}>
                <span className="feed-icon">
                  <Icon size={13} />
                </span>
                <div>
                  <p>{event.summary}</p>
                  <small>
                    {relativeTime(event.at)} · {event.actor}
                  </small>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
