import { useEffect, useState } from "react";
import { fetchJSON, TTL } from "./fetchJSON";

/**
 * Poll a JSON endpoint on an interval through the shared fetchJSON layer
 * (in-flight dedup + short TTL), keeping the last good payload on failure —
 * the standard pattern every new-surface box uses. Pair with <StaleBadge/>
 * for honesty when the backend stops answering (Fix 9).
 */
export function usePoll<T>(url: string, intervalMs = 10_000): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    if (!url) return; // conditional polling: empty url = off (keeps last data)
    let stop = false;
    const load = () =>
      fetchJSON<T>(url, { ttlMs: TTL.short })
        .then((d) => { if (!stop && d != null) setData(d); })
        .catch(() => {});
    load();
    const id = setInterval(load, intervalMs);
    return () => { stop = true; clearInterval(id); };
  }, [url, intervalMs]);
  return data;
}
