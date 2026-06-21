import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Search } from "lucide-react";
import { API, colorFor } from "@/lib/cognitive";
import { fetchJSON } from "@/lib/fetchJSON";
import { FnCatalog, FnEvent } from "@/lib/telemetry";
import { type Settings } from "./layout";
import { Seg } from "./ControlsPanel";

function relTime(ts?: string | number): string {
  if (ts == null) return "";
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  const ms = Date.now() - d.getTime();
  if (isNaN(ms)) return "";
  if (ms < 15_000) return "now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h`;
  return `${Math.round(ms / 86_400_000)}d`;
}

// ── left-side function explorer (for someone who reads code) ──────────────────
export function CognitionExplorer({
  catalog,
  settings,
  setSettings,
  activeFn,
  fnRecent,
  query,
  setQuery,
  onPick,
  focusNode,
}: {
  catalog: FnCatalog;
  settings: Settings;
  setSettings: (s: Settings) => void;
  activeFn: string | null;
  fnRecent: FnEvent[];
  query: string;
  setQuery: (q: string) => void;
  onPick: (n: string) => void;
  focusNode: string | null;
}) {
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [view, setView] = useState<"functions" | "history">("functions");
  type HistoryEvent = { fn: string; reward: number | null; agentic: boolean | null; ts?: string; lane?: string | null };
  const [history, setHistory] = useState<HistoryEvent[]>([]);
  const activeSub = activeFn ? catalog.functions[activeFn]?.subsystem ?? null : null;

  // Poll the activation history while the History tab is open.
  useEffect(() => {
    if (view !== "history") return;
    let stop = false;
    const load = () =>
      fetchJSON<{ events?: HistoryEvent[] }>(`${API}/history?n=120`)
        .then((d) => { if (!stop && Array.isArray(d.events)) setHistory(d.events); })
        .catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [view, activeFn]);

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const subs = Object.keys(catalog.subsystems).sort((a, b) => catalog.subsystems[b].length - catalog.subsystems[a].length);
    return subs
      .filter((s) => !settings.hiddenSubs[s])
      .map((sub) => {
        let fns = catalog.subsystems[sub].map((n) => catalog.functions[n]).filter(Boolean);
        if (settings.onlyUsed) fns = fns.filter((f) => (f.count || 0) > 0);
        if (q) fns = fns.filter((f) => f.name.toLowerCase().includes(q));
        if (settings.sort === "usage") fns.sort((a, b) => (b.count || 0) - (a.count || 0));
        else if (settings.sort === "name") fns.sort((a, b) => a.name.localeCompare(b.name));
        return { sub, fns };
      })
      .filter((g) => g.fns.length);
  }, [catalog, settings.onlyUsed, settings.sort, settings.hiddenSubs, query]);

  const total = groups.reduce((n, g) => n + g.fns.length, 0);

  return (
    <div className="flex w-64 flex-none flex-col border-r border-border bg-card/40">
      {/* tabs: live function map vs. activation history */}
      <div className="flex border-b border-border">
        {(["functions", "history"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setView(t)}
            className={`flex-1 px-2 py-1.5 text-[11px] font-medium capitalize transition-colors ${
              view === t ? "border-b-2 border-foreground text-foreground" : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {view === "functions" && (
        <>
      {/* search + sort */}
      <div className="space-y-1.5 border-b border-border p-2">
        <div className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1">
          <Search className="h-3.5 w-3.5 text-muted-foreground" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter functions…"
            className="w-full bg-transparent text-[11px] outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">{total} shown</span>
          <Seg
            value={settings.sort}
            opts={[["usage", "Usage"], ["name", "Name"], ["subsystem", "Group"]]}
            set={(v) => setSettings({ ...settings, sort: v as Settings["sort"] })}
          />
        </div>
      </div>

      {/* now running */}
      {activeFn && (
        <div className="border-b border-border px-2 py-1.5">
          <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Now running</div>
          <button onClick={() => onPick(activeFn)} className="mt-0.5 flex w-full items-center gap-1.5 text-left">
            <span className="h-2 w-2 flex-none animate-pulse rounded-full" style={{ background: colorFor(activeSub || "Other") }} />
            <span className="truncate font-mono text-[11px] font-semibold text-foreground">{activeFn}</span>
          </button>
          {fnRecent.length > 1 && (
            <div className="mt-1 flex flex-wrap gap-1">
              {[...fnRecent].slice(-5, -1).reverse().map((e, i) => (
                <button
                  key={i}
                  onClick={() => onPick(e.fn)}
                  className="truncate rounded bg-muted px-1 py-0.5 font-mono text-[9px] text-muted-foreground hover:text-foreground"
                  style={{ maxWidth: 110 }}
                  title={e.fn}
                >
                  {e.fn}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* grouped function list */}
      <div className="min-h-0 flex-1 overflow-y-auto py-1">
        {groups.map((g) => {
          const color = colorFor(g.sub);
          const isCollapsed = collapsed[g.sub];
          const hasActive = g.sub === activeSub;
          return (
            <div key={g.sub}>
              <button
                onClick={() => setCollapsed((c) => ({ ...c, [g.sub]: !c[g.sub] }))}
                className="flex w-full items-center gap-1.5 px-2 py-1 text-left hover:bg-muted/50"
              >
                <ChevronDown className={`h-3 w-3 flex-none text-muted-foreground transition-transform ${isCollapsed ? "-rotate-90" : ""}`} />
                <span className="h-2 w-2 flex-none rounded-full" style={{ background: color }} />
                <span className="flex-1 truncate text-[11px] font-semibold text-foreground">{g.sub}</span>
                {hasActive && <span className="h-1.5 w-1.5 flex-none animate-pulse rounded-full" style={{ background: color }} />}
                <span className="text-[9px] text-muted-foreground">{g.fns.length}</span>
              </button>
              {!isCollapsed &&
                g.fns.map((f) => {
                  const isActive = f.name === activeFn;
                  const isFocus = f.name === focusNode;
                  return (
                    <button
                      key={f.name}
                      onClick={() => onPick(f.name)}
                      className={`flex w-full items-center gap-1.5 py-0.5 pl-6 pr-2 text-left transition-colors ${
                        isActive ? "bg-foreground/10" : isFocus ? "bg-muted" : "hover:bg-muted/60"
                      }`}
                      title={f.summary || f.name}
                    >
                      <span
                        className={`h-1.5 w-1.5 flex-none rounded-full ${isActive ? "animate-pulse" : ""}`}
                        style={{ background: color, opacity: (f.count || 0) > 0 || isActive ? 1 : 0.35 }}
                      />
                      <span className={`flex-1 truncate font-mono text-[10px] ${isActive ? "font-semibold text-foreground" : (f.count || 0) > 0 ? "text-foreground/85" : "text-muted-foreground"}`}>
                        {f.name}
                      </span>
                      {(f.count || 0) > 0 && <span className="font-mono text-[9px] text-muted-foreground tabular-nums">{f.count}</span>}
                    </button>
                  );
                })}
            </div>
          );
        })}
        {total === 0 && <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">No functions match.</div>}
      </div>
        </>
      )}

      {view === "history" && (
        <div className="min-h-0 flex-1 overflow-y-auto p-1">
          <div className="px-2 py-1 text-[9px] text-muted-foreground">most recent first · click to inspect</div>
          {history.length === 0 && <div className="px-3 py-4 text-center text-[11px] text-muted-foreground">No activation history yet.</div>}
          {[...history].reverse().map((e, i) => {
            const info = e.fn ? catalog.functions[e.fn] : undefined;
            const color = colorFor(info?.subsystem || "Other");
            const isLatest = i === 0;
            return (
              <button
                key={`${i}-${e.fn}`}
                onClick={() => e.fn && onPick(e.fn)}
                className={`flex w-full items-center gap-1.5 rounded px-2 py-1 text-left hover:bg-muted/60 ${isLatest ? "bg-foreground/10" : ""}`}
                title={info?.summary || e.fn || ""}
              >
                <span className={`h-1.5 w-1.5 flex-none rounded-full ${isLatest ? "animate-pulse" : ""}`} style={{ background: color }} />
                <span className="flex-1 truncate font-mono text-[10px] text-foreground/85">{e.fn}</span>
                {e.lane === "executive" && (
                  <span className="rounded px-1 text-[8px] font-semibold" style={{ background: "#f59e0b22", color: "#f59e0b" }} title="Executive lane (autopilot)">exec</span>
                )}
                {e.agentic && <span className="rounded bg-signal-ok/15 px-1 text-[8px] font-semibold text-signal-ok">act</span>}
                {e.reward != null && (
                  <span
                    className="font-mono text-[9px] tabular-nums"
                    style={{ color: e.reward >= 0.45 ? "hsl(var(--signal-ok))" : e.reward < 0.2 ? "hsl(var(--signal-error))" : "hsl(var(--muted-foreground))" }}
                  >
                    {Math.round(e.reward * 100)}
                  </span>
                )}
                {e.ts && (
                  <span className="w-9 flex-none text-right font-mono text-[9px] tabular-nums text-muted-foreground/60" title={new Date(e.ts).toLocaleString()}>
                    {relTime(e.ts)}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
