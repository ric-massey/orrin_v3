import { useEffect, useState } from "react";
import { Code2, X } from "lucide-react";
import { API } from "@/lib/cognitive";
import { fetchJSON, TTL } from "@/lib/fetchJSON";
import { MetricDef, SrcRef } from "@/lib/metricDefs";
import { PerspectiveBadge } from "./PerspectiveBadge";

// Shared metric info popover (UI_FIXES Fix 6): the full info "page" for one
// signal — what it is, the terms, how it's measured, the 0–100 scale, and (on
// demand) the real source code. Extracted from MetricsStrip so ControlSignalRings'
// rings/bars get the same ℹ️ → Code chain the metrics legend already had.

// Scrollable view of the real code behind a number — the L5 leaf every drawer
// ends in. Exported so the new-surface boxes' About popovers reuse it.
export function SourceCode({ src }: { src: SrcRef }) {
  const [code, setCode] = useState<{ s: string; loading: boolean; err?: string }>({ s: "", loading: true });
  useEffect(() => {
    setCode({ s: "", loading: true });
    fetchJSON<{ source?: string; error?: string }>(`${API}/source?file=${encodeURIComponent(src.file)}&start=${src.start}&end=${src.end}`, { ttlMs: TTL.immutable })
      .then((d) => setCode({ s: d.source || "", loading: false, err: d.error }))
      .catch((e) => setCode({ s: "", loading: false, err: String(e) }));
  }, [src.file, src.start, src.end]);
  return (
    <div className="mt-2 border-t border-border/60 pt-2">
      <div className="mb-1 flex items-center gap-1 text-[10px] text-muted-foreground">
        <Code2 className="h-3 w-3" />
        <span className="truncate">{src.label}</span>
        <span className="ml-auto font-mono text-muted-foreground/70">{src.file.split("/").pop()}:{src.start}</span>
      </div>
      {code.loading && <div className="text-[10px] text-muted-foreground">Loading source…</div>}
      {code.err && <div className="text-[10px] text-signal-error">Couldn't load: {code.err}</div>}
      {code.s && (
        <pre className="max-h-56 overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-snug">
          <code className="font-mono">{code.s}</code>
        </pre>
      )}
    </div>
  );
}

export default function MetricInfo({ m, onClose, className }: { m: MetricDef; onClose: () => void; className?: string }) {
  const [showCode, setShowCode] = useState(false);
  return (
    <div className={className ?? "absolute left-0 top-6 z-30 max-h-[60vh] w-80 overflow-auto rounded-lg border border-border bg-popover p-3 text-left shadow-2xl"}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: m.color }} />
        <span className="text-[13px] font-semibold text-foreground">{m.label}</span>
        <PerspectiveBadge layer={m.perspective} />
        <button onClick={onClose} aria-label="Close" className="ml-auto rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <p className="text-[11px] leading-relaxed text-foreground/90">{m.long}</p>

      {m.terms && m.terms.length > 0 && (
        <div className="mt-2 space-y-1.5">
          {m.terms.map((t) => (
            <div key={t.t} className="text-[10.5px] leading-snug">
              <span className="font-semibold text-foreground">{t.t}</span>
              <span className="text-muted-foreground"> — {t.d}</span>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2 rounded-md bg-muted/40 p-2">
        <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">How it's measured</div>
        <p className="mt-0.5 text-[10.5px] leading-snug text-foreground/85">{m.measure}</p>
      </div>

      {/* 0–100 scale legend */}
      <div className="mt-2 border-t border-border/60 pt-2">
        <div className="flex items-center justify-between text-[10px] text-muted-foreground">
          <span>0 · {m.lo}</span>
          {m.bipolar && <span>50 · neutral</span>}
          <span>{m.hi} · 100</span>
        </div>
        <div className="mt-1 h-1.5 w-full rounded-full" style={{ background: `linear-gradient(90deg, transparent, ${m.color})` }} />
        <div className="mt-1.5 text-[10px] leading-snug text-muted-foreground/80">
          Shown as a <span className="font-medium text-foreground/80">level (0–100)</span> — normalized intensity{m.bipolar ? ", 50 = neutral." : "."}
        </div>
      </div>

      {m.src && (
        <>
          <button
            onClick={() => setShowCode((v) => !v)}
            className="mt-2 flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <Code2 className="h-3 w-3" /> {showCode ? "Hide code" : "Show the code that computes this"}
          </button>
          {showCode && <SourceCode src={m.src} />}
        </>
      )}
    </div>
  );
}
