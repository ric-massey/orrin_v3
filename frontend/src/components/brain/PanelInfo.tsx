import { useEffect, useRef, useState } from "react";
import { Code2, Info, X } from "lucide-react";
import { SrcRef } from "@/lib/metricDefs";
import { SourceCode } from "./MetricInfo";
import { PerspectiveBadge, PerspectiveLayer } from "./PerspectiveBadge";

/**
 * Per-panel "About" popover (UI_FIXES Fix 11, seeded for the new-surface
 * boxes): plain-language — what this box shows, where the data comes from,
 * what "good" looks like — ending in the same /source code leaf as everything
 * else. One shared component; the per-panel copy is the only real work.
 */
export default function PanelInfo({
  title,
  what,
  source,
  good,
  src,
  perspective,
}: {
  title: string;
  /** What this box shows, in plain language. */
  what: string;
  /** Where the data comes from (file / module). */
  source?: string;
  /** What "good" looks like / what to watch for. */
  good?: string;
  /** Optional code leaf (L5). */
  src?: SrcRef;
  /** Whose perspective this panel belongs to (UI plan §5.3). */
  perspective?: PerspectiveLayer;
}) {
  const [open, setOpen] = useState(false);
  const [showCode, setShowCode] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  return (
    <span className="relative" ref={ref}>
      <PerspectiveBadge layer={perspective} className="mr-0.5 align-middle" />
      <button
        onClick={() => setOpen((v) => !v)}
        className="rounded p-0.5 text-muted-foreground/50 hover:bg-muted hover:text-foreground"
        aria-label={`About ${title}`}
      >
        <Info className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute left-0 top-5 z-40 max-h-[55vh] w-80 overflow-auto rounded-lg border border-border bg-popover p-3 text-left shadow-2xl">
          <div className="mb-1.5 flex items-center gap-1.5">
            <span className="text-[13px] font-semibold text-foreground">{title}</span>
            <PerspectiveBadge layer={perspective} />
            <button onClick={() => setOpen(false)} aria-label="Close" className="ml-auto rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
          <p className="text-[11px] leading-relaxed text-foreground/90">{what}</p>
          {source && (
            <div className="mt-2 rounded-md bg-muted/40 p-2">
              <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Where this comes from</div>
              <p className="mt-0.5 font-mono text-[10px] leading-snug text-foreground/85">{source}</p>
            </div>
          )}
          {good && (
            <div className="mt-2">
              <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">What good looks like</div>
              <p className="mt-0.5 text-[10.5px] leading-snug text-foreground/85">{good}</p>
            </div>
          )}
          {src && (
            <>
              <button
                onClick={() => setShowCode((v) => !v)}
                className="mt-2 flex items-center gap-1.5 rounded-md border border-border px-2 py-1 text-[10px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <Code2 className="h-3 w-3" /> {showCode ? "Hide code" : "Show the code behind this"}
              </button>
              {showCode && <SourceCode src={src} />}
            </>
          )}
        </div>
      )}
    </span>
  );
}
