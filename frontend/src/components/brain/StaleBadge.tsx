import { useEffect, useState } from "react";
import { lastSuccessAt } from "@/lib/fetchJSON";

/**
 * Staleness honesty for REST-fed panels (UI_FIXES Fix 9). The pollers keep
 * their last good data on fetch failure (good anti-flicker), which means a
 * dead backend produces a panel that looks healthy and is silently frozen.
 * This badge reads fetchJSON's per-URL lastSuccess clock and says so:
 * a quiet "12s" while fresh, an amber "stale 2m" once the data is older than
 * ~3 poll intervals.
 */
export default function StaleBadge({
  url,
  prefix = true,
  pollMs = 3000,
}: {
  /** The polled URL (or URL prefix, e.g. `${API}/history`) to watch. */
  url: string;
  /** Prefix-match the URL so query-string variants count. */
  prefix?: boolean;
  /** The panel's poll interval; stale = older than ~3 of these. */
  pollMs?: number;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => tick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, []);

  const ts = lastSuccessAt(url, prefix);
  if (!ts) return null; // nothing fetched yet — the panel's own empty state covers this
  const age = Date.now() - ts;
  const stale = age > Math.max(pollMs * 3, 10_000);
  const label = age < 60_000 ? `${Math.max(1, Math.round(age / 1000))}s` : age < 3_600_000 ? `${Math.round(age / 60_000)}m` : `${Math.round(age / 3_600_000)}h`;

  if (!stale) {
    return (
      <span className="text-[9px] tabular-nums text-muted-foreground/50" title={`Last updated ${label} ago`}>
        {label}
      </span>
    );
  }
  return (
    <span
      className="rounded bg-signal-warn/15 px-1.5 py-0.5 text-[9px] font-semibold tabular-nums text-signal-warn"
      title={`No successful fetch for ${label} — this panel is showing OLD data (backend down or unreachable).`}
    >
      stale {label}
    </span>
  );
}
