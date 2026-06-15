import { useEffect, useState } from "react";
import { apiGet } from "./transport";

/**
 * Poll a JSON API path on an interval through the active transport (HTTP in the
 * browser, the in-process bridge in the native window). Returns the last good value,
 * or null until the first success — callers render an honest-empty state in the
 * meantime rather than blank (§9.3 honesty rule). Keeps the last value on error.
 */
export function usePolledJSON<T>(path: string, intervalMs = 4000): T | null {
  const [data, setData] = useState<T | null>(null);
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      try {
        const res = await apiGet(path);
        if (res.ok && alive) setData((await res.json()) as T);
      } catch {
        /* keep last good value */
      }
    };
    void tick();
    const id = window.setInterval(tick, intervalMs);
    return () => {
      alive = false;
      window.clearInterval(id);
    };
  }, [path, intervalMs]);
  return data;
}
