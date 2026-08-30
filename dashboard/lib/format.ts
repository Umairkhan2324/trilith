import type { Scope, Tier } from "./types";

export function relativeTime(value: string | number): string {
  const then = typeof value === "number" ? value * 1000 : new Date(value).getTime();
  if (!Number.isFinite(then)) return "";
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export function absoluteTime(value: string | number): string {
  const date = typeof value === "number" ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.getTime()) ? "" : date.toLocaleString();
}

/** Seconds until an expiry, phrased for a badge. Past expiries read as expired. */
export function expiryLabel(expiresAt: string | null): string | null {
  if (!expiresAt) return null;
  const remaining = (new Date(expiresAt).getTime() - Date.now()) / 1000;
  if (!Number.isFinite(remaining)) return null;
  if (remaining <= 0) return "expired";
  if (remaining < 60) return `expires in ${Math.round(remaining)}s`;
  if (remaining < 3600) return `expires in ${Math.round(remaining / 60)}m`;
  if (remaining < 86400) return `expires in ${Math.round(remaining / 3600)}h`;
  return `expires in ${Math.round(remaining / 86400)}d`;
}

export const tierLabel: Record<Tier, string> = {
  SEMANTIC: "Semantic",
  PROCEDURAL: "Procedural",
  EPISODIC: "Episodic",
};

export const tierNote: Record<Tier, string> = {
  SEMANTIC: "Durable facts",
  PROCEDURAL: "Task steps",
  EPISODIC: "Scoped events",
};

export const scopeNote: Record<Scope, string> = {
  GLOBAL: "Readable by every tenant",
  TENANT: "Readable across this tenant",
  USER: "Readable by one owner",
  SESSION: "Readable in one session",
  SCOPE_UNSPECIFIED: "No scope set",
};

export function truncate(text: string, width = 140): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length <= width ? clean : `${clean.slice(0, width - 1)}…`;
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
