// Shared JSON fetch layer with in-flight de-duplication + optional TTL cache.
//
// Why (UI_AUDIT M2 — "thundering herd"): several Brain panels each poll the
// backend on independent timers (goals 3s, history 3s, catalog retry 2s) and
// re-issue per-open fetches (/code, /source, /goal_artifacts) on every mount.
// Nothing coordinated them, so concurrent identical requests and remount bursts
// duplicated work.
//
// This module gives every caller one front door:
//   • In-flight de-duplication — concurrent requests for the SAME url share a
//     single network call (the headline fix; safe for every endpoint).
//   • Optional TTL cache — for immutable data (source code never changes at
//     runtime) so re-opening the same drawer doesn't refetch. Pollers pass
//     ttlMs:0 so their freshness is unchanged.
//
// It is intentionally tiny and dependency-free (no react-query) per the audit's
// "even a hand-rolled fetchJSON with a TTL cache" guidance.

type CacheEntry = { ts: number; data: unknown };

const cache = new Map<string, CacheEntry>();
const pending = new Map<string, Promise<unknown>>();
// Per-URL timestamp of the last 2xx response (Fix 9 — staleness honesty):
// polling panels keep their last good data on failure (good anti-flicker),
// so this is the only signal that the data on screen is actually old.
const lastOk = new Map<string, number>();

/** Epoch-ms of the last successful fetch for `url` (prefix-matched when
 *  `prefix` is true, so pollers with query params can be tracked by base). */
export function lastSuccessAt(url: string, prefix = false): number | undefined {
  if (!prefix) return lastOk.get(url);
  let best: number | undefined;
  for (const [k, v] of lastOk) {
    if (k.startsWith(url) && (best === undefined || v > best)) best = v;
  }
  return best;
}

export interface FetchJSONOpts {
  /** Serve a cached body younger than this many ms. 0 (default) = never cache. */
  ttlMs?: number;
  /** Bypass cache and any in-flight share; always issue a fresh request. */
  force?: boolean;
}

/**
 * Fetch and parse JSON, de-duplicating concurrent identical requests and
 * (optionally) caching the result for `ttlMs`.
 *
 * Mirrors the previous call sites' behavior: the body is parsed regardless of
 * HTTP status (the backend returns `{ error }` on failures), but only `r.ok`
 * responses are cached, so a transient 500 is never memoized.
 */
export async function fetchJSON<T = unknown>(url: string, opts: FetchJSONOpts = {}): Promise<T> {
  const { ttlMs = 0, force = false } = opts;

  if (!force && ttlMs > 0) {
    const hit = cache.get(url);
    if (hit && Date.now() - hit.ts < ttlMs) return hit.data as T;
  }

  if (!force) {
    const inflight = pending.get(url);
    if (inflight) return inflight as Promise<T>;
  }

  const p = (async () => {
    const r = await fetch(url);
    const data = (await r.json()) as T;
    if (r.ok) {
      lastOk.set(url, Date.now());
      if (ttlMs > 0) cache.set(url, { ts: Date.now(), data });
    }
    return data;
  })().finally(() => {
    pending.delete(url);
  });

  pending.set(url, p);
  return p as Promise<T>;
}

/** Drop a cached URL (or the whole cache) — call after a known mutation. */
export function invalidate(url?: string): void {
  if (url) cache.delete(url);
  else cache.clear();
}

/** Cache lifetimes used across the Brain panels. */
export const TTL = {
  /** Source code / catalog are immutable within a session. */
  immutable: 5 * 60_000,
  /** Per-open artifact lists change slowly; a few seconds dedups remount bursts. */
  short: 3_000,
} as const;
