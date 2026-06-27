import { useEffect, useMemo, useRef, useState } from "react";
import { Pause, Play, Search, Terminal, Trash2 } from "lucide-react";
import { LogLevel, LogLine, TelemetryState } from "@/lib/telemetry";
import { cn, fmtTime } from "@/lib/utils";

const LEVELS: { key: LogLevel; label: string; color: string; dot: string }[] = [
  { key: "debug", label: "DEBUG", color: "text-muted-foreground", dot: "bg-muted-foreground" },
  { key: "info", label: "INFO", color: "text-signal-info", dot: "bg-signal-info" },
  { key: "warn", label: "WARN", color: "text-signal-warn", dot: "bg-signal-warn" },
  { key: "error", label: "ERROR", color: "text-signal-error", dot: "bg-signal-error" },
  { key: "critical", label: "CRIT", color: "text-signal-error", dot: "bg-signal-error" },
];
const LEVEL_MAP = Object.fromEntries(LEVELS.map((l) => [l.key, l]));
const RANK: Record<LogLevel, number> = { debug: 0, info: 1, warn: 2, error: 3, critical: 4 };

// Throttle window: re-render the console at most this often, regardless of how
// fast log frames arrive over the WebSocket. Decouples high-frequency telemetry
// from React re-renders.
const FLUSH_MS = 150;
// Hard cap on rendered lines to prevent browser memory bloat.
const MAX_LINES = 500;

export default function LiveConsole({ telemetry }: { telemetry: TelemetryState }) {
  const [minLevel, setMinLevel] = useState<LogLevel>("debug");
  const [paused, setPaused] = useState(false);
  const [clearedTs, setClearedTs] = useState(0);
  // Fix 10.2: a level filter alone is not enough as sources multiply — add
  // clickable source chips (derived from the visible ring) and a text search.
  const [sourceSel, setSourceSel] = useState<Set<string>>(new Set());
  const [q, setQ] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // ── Throttled buffer ──────────────────────────────────────────────────────
  // telemetry.logs updates on every frame; we copy the latest slice into local
  // state on a fixed 150ms cadence instead of re-rendering per log line.
  const logsRef = useRef<LogLine[]>(telemetry.logs);
  logsRef.current = telemetry.logs;
  const [view, setView] = useState<LogLine[]>(() => telemetry.logs.slice(-MAX_LINES));
  const lastFlushed = useRef<LogLine[]>(telemetry.logs);

  useEffect(() => {
    const id = window.setInterval(() => {
      const latest = logsRef.current;
      if (latest === lastFlushed.current) return; // ring reference unchanged → no work
      lastFlushed.current = latest;
      setView(latest.slice(-MAX_LINES));
    }, FLUSH_MS);
    return () => window.clearInterval(id);
  }, []);

  const sources = useMemo(() => {
    const c = new Map<string, number>();
    for (const l of view) {
      if (l.source) c.set(l.source, (c.get(l.source) || 0) + 1);
    }
    return [...c.entries()].sort((a, b) => b[1] - a[1]).slice(0, 10);
  }, [view]);

  const toggleSource = (s: string) =>
    setSourceSel((cur) => {
      const next = new Set(cur);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  const visible = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return view.filter(
      (l) =>
        RANK[l.level] >= RANK[minLevel] &&
        (l.ts == null || l.ts > clearedTs) &&
        (sourceSel.size === 0 || sourceSel.has(l.source)) &&
        (!needle || `${l.source} ${l.message}`.toLowerCase().includes(needle))
    );
  }, [view, minLevel, clearedTs, sourceSel, q]);

  useEffect(() => {
    if (paused) return;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [visible, paused]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border bg-[hsl(240_10%_3%)] text-[hsl(0_0%_88%)] shadow-sm">
      {/* toolbar — also the Fix 3 drag handle (this panel has no CardHeader) */}
      <div className="card-drag flex flex-wrap items-center justify-between gap-2 border-b border-white/10 bg-white/[0.03] px-3 py-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2 text-xs font-medium text-white/70">
          <Terminal className="h-3.5 w-3.5" />
          Live Console
          <span className="hidden text-[10px] font-normal text-white/30 lg:inline">— everything the subsystems report, live</span>
          <span className="text-white/30">·</span>
          <span className="tabular-nums text-white/40">{visible.length} lines</span>
        </div>
        <div className="flex min-w-0 flex-wrap items-center gap-1.5">
          {LEVELS.slice(0, 4).map((l) => (
            <button
              key={l.key}
              onClick={() => setMinLevel(l.key)}
              className={cn(
                "flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold tracking-wide transition-colors",
                minLevel === l.key ? "bg-white/10 text-white" : "text-white/40 hover:text-white/70"
              )}
              title={`Show ${l.label} and above`}
            >
              <span className={cn("h-1.5 w-1.5 rounded-full", l.dot)} />
              {l.label}
            </button>
          ))}
          <div className="mx-1 h-4 w-px bg-white/10" />
          <button
            onClick={() => setPaused((p) => !p)}
            className="rounded p-1 text-white/50 hover:bg-white/10 hover:text-white"
            title={paused ? "Resume autoscroll" : "Pause autoscroll"}
          >
            {paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
          </button>
          <button
            onClick={() => setClearedTs(Date.now() / 1000)}
            className="rounded p-1 text-white/50 hover:bg-white/10 hover:text-white"
            title="Clear console"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* source chips + search (Fix 10.2) */}
      <div className="flex flex-wrap items-center gap-1 border-b border-white/10 px-3 py-1.5">
        <div className="mr-1 flex items-center gap-1 rounded border border-white/10 bg-white/[0.04] px-1.5 py-0.5">
          <Search className="h-3 w-3 text-white/30" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search…"
            className="w-24 bg-transparent text-[10px] text-white/80 outline-none placeholder:text-white/25"
          />
        </div>
        {sources.map(([s, n]) => {
          const on = sourceSel.has(s);
          return (
            <button
              key={s}
              onClick={() => toggleSource(s)}
              className={cn(
                "rounded px-1.5 py-0.5 text-[9.5px] font-medium transition-colors",
                on ? "bg-signal-accent/25 text-signal-accent" : "text-white/40 hover:text-white/70"
              )}
              title={on ? `Showing only selected sources — click to remove ${s}` : `Show only ${s} (${n} lines)`}
            >
              {s}
              <span className="ml-1 text-white/25 tabular-nums">{n}</span>
            </button>
          );
        })}
        {sourceSel.size > 0 && (
          <button onClick={() => setSourceSel(new Set())} className="rounded px-1.5 py-0.5 text-[9.5px] text-white/40 underline hover:text-white/70">
            all sources
          </button>
        )}
      </div>

      {/* stream */}
      <div ref={scrollRef} className="scrollbar-thin flex-1 overflow-auto px-3 py-2 font-mono text-[11.5px] leading-relaxed">
        {visible.length === 0 ? (
          <div className="py-8 text-center text-white/30">No log lines at this severity.</div>
        ) : (
          visible.map((l, i) => <Line key={(l.ts ?? 0) + ":" + i} line={l} />)
        )}
      </div>
    </div>
  );
}

function Line({ line }: { line: LogLine }) {
  const meta = LEVEL_MAP[line.level] ?? LEVEL_MAP.info;
  return (
    <div className="flex gap-2 whitespace-pre-wrap py-0.5 hover:bg-white/[0.03]">
      <span className="shrink-0 text-white/30">{fmtTime(line.ts)}</span>
      <span className={cn("w-12 shrink-0 font-semibold", meta.color)}>{meta.label}</span>
      <span className="shrink-0 text-signal-accent/80">{line.source}</span>
      <span className="text-white/85">{line.message}</span>
    </div>
  );
}
