import { useState } from "react";
import { Info, X } from "lucide-react";
import { SourceCode } from "./MetricInfo";
import type { SrcRef } from "@/lib/metricDefs";

// Part 8 acceptance bar: every value on the calm rooms (Cognition/Life/Memory/Timeline)
// must drill down to the real code that produces it — the same ℹ️ → source chain Brain's
// metrics already have, but lighter (these are feeds, not 0–100 signals). One ℹ️ per
// value-group opens a short "what this is" note and the exact source slice via the shared
// SourceCode leaf (GET /source). Reuses MetricInfo's SourceCode so there's one code path.

export interface ValueInfo {
  label: string;
  what: string;
  src: SrcRef;
}

export default function InfoDot({ info, className }: { info: ValueInfo; className?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className={`relative inline-flex ${className ?? ""}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={`About ${info.label}`}
        className="inline-flex items-center rounded p-0.5 text-muted-foreground/70 hover:bg-muted hover:text-foreground"
      >
        <Info className="h-3.5 w-3.5" />
      </button>
      {open && (
        <>
          {/* click-away */}
          <span className="fixed inset-0 z-20" onClick={() => setOpen(false)} />
          <div className="absolute left-0 top-6 z-30 max-h-[60vh] w-80 overflow-auto rounded-lg border border-border bg-popover p-3 text-left shadow-2xl">
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className="text-[13px] font-semibold text-foreground">{info.label}</span>
              <button
                onClick={() => setOpen(false)}
                aria-label="Close"
                className="ml-auto rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
            <p className="text-[11px] leading-relaxed text-foreground/90">{info.what}</p>
            <SourceCode src={info.src} />
          </div>
        </>
      )}
    </span>
  );
}
