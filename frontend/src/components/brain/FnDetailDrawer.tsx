import { useEffect, useState } from "react";
import { Activity, ArrowLeft, BarChart3, Code2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";
import { API, colorFor } from "@/lib/cognitive";
import { fetchJSON, TTL } from "@/lib/fetchJSON";
import { CatalogFn, FnEvent } from "@/lib/telemetry";

type Tab = "about" | "stats" | "activity" | "code";

function Row({ k, v, mono }: { k: string; v: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <span className="text-[11px] uppercase tracking-wide text-muted-foreground/70">{k}</span>
      <span className={cn("text-right text-foreground/90", mono && "font-mono text-[11px]")}>{v}</span>
    </div>
  );
}

/** Slide-in panel describing one cognitive function: About / Stats / Activity / Code. */
export default function FnDetailDrawer({
  fn,
  info,
  recent,
  onClose,
}: {
  fn: string;
  info: CatalogFn | undefined;
  recent: FnEvent[];
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("about");
  const [code, setCode] = useState<{ source: string; loading: boolean; err?: string }>({ source: "", loading: false });
  const color = colorFor(info?.subsystem || "Other");

  useEffect(() => {
    setTab("about");
    setCode({ source: "", loading: false });
  }, [fn]);

  useEffect(() => {
    if (tab !== "code" || code.source || code.loading) return;
    setCode({ source: "", loading: true });
    fetchJSON<{ source?: string; error?: string }>(`${API}/code?fn=${encodeURIComponent(fn)}`, { ttlMs: TTL.immutable })
      .then((d) => setCode({ source: d.source || "", loading: false, err: d.error }))
      .catch((e) => setCode({ source: "", loading: false, err: String(e) }));
  }, [tab, fn, code.source, code.loading]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const fires = recent.filter((r) => r.fn === fn);
  const tabs: { key: Tab; label: string; icon: React.ReactNode }[] = [
    { key: "about", label: "About", icon: <Info className="h-3.5 w-3.5" /> },
    { key: "stats", label: "Stats", icon: <BarChart3 className="h-3.5 w-3.5" /> },
    { key: "activity", label: "Activity", icon: <Activity className="h-3.5 w-3.5" /> },
    { key: "code", label: "Code", icon: <Code2 className="h-3.5 w-3.5" /> },
  ];

  return (
    <div role="dialog" aria-modal="true" aria-label="Function details" className="absolute inset-y-0 right-0 z-30 flex w-[min(380px,82%)] flex-col border-l border-border bg-card/95 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        <span className="min-w-0 flex-1 truncate font-mono text-[13px] font-semibold">{fn}</span>
        <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ background: `${color}22`, color }}>
          {info?.subsystem || "Other"}
        </span>
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex border-b border-border px-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "flex items-center gap-1.5 border-b-2 px-2.5 py-2 text-[11px] font-medium transition-colors",
              tab === t.key ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {t.icon}
            {t.label}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3 text-[12px]">
        {tab === "about" && (
          <div className="space-y-2">
            <p className="leading-relaxed text-foreground/90">{info?.summary || "No description available."}</p>
            <div className="space-y-1 border-t border-border/60 pt-2 text-muted-foreground">
              <Row k="Subsystem" v={info?.subsystem || "—"} />
              <Row k="Kind" v={info?.kind || "—"} />
              <Row k="Source" v={info ? `${info.file}:${info.lineno}` : "—"} mono />
            </div>
          </div>
        )}
        {tab === "stats" && (
          <div className="space-y-1.5 text-muted-foreground">
            <Row k="Times chosen" v={`${info?.count ?? 0}`} />
            <Row k="Avg reward" v={`${((info?.avg_reward ?? 0) * 100).toFixed(0)} / 100`} />
            <Row k="Recent firings" v={`${fires.length} (live window)`} />
            {(info?.count ?? 0) === 0 && <p className="pt-1 text-[11px] text-muted-foreground/70">It hasn't used this one yet.</p>}
          </div>
        )}
        {tab === "activity" && (
          <div className="space-y-1.5">
            {fires.length === 0 && <p className="text-muted-foreground/70">No recent firings in the live window.</p>}
            {fires
              .slice()
              .reverse()
              .map((r, i) => (
                <div key={i} className="flex items-center justify-between rounded-md border border-border/60 px-2.5 py-1.5">
                  <span className="text-muted-foreground">cycle {r.cycle ?? "—"}</span>
                  {r.reward != null && (
                    <span className="font-mono" style={{ color }}>
                      reward {Math.round((r.reward as number) * 100)}
                    </span>
                  )}
                </div>
              ))}
          </div>
        )}
        {tab === "code" && (
          <div>
            {code.loading && <p className="text-muted-foreground">Loading source…</p>}
            {code.err && <p className="text-signal-error">Couldn't load: {code.err}</p>}
            {code.source && (
              <pre className="overflow-auto rounded-md bg-muted/40 p-2.5 text-[11px] leading-snug">
                <code className="font-mono">{code.source}</code>
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
