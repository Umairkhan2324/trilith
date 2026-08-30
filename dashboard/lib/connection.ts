import { ApiError, OfflineError } from "./api";

export type Connection = "connecting" | "online" | "offline" | "unauthorized";

/**
 * What a failed call means for the console as a whole.
 *
 * The three cases are genuinely different and the interface must not blur
 * them: nothing is listening, something is listening but will not talk to you
 * without a key, or the request itself was wrong.
 */
export function classify(error: unknown): Connection | null {
  if (error instanceof OfflineError) return "offline";
  if (error instanceof ApiError && error.status === 401) return "unauthorized";
  return null;
}

export function describeError(error: unknown): string {
  if (error instanceof OfflineError) return "Trilith Core is not reachable";
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Unexpected error";
}
