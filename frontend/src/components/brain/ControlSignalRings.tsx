import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Affect } from "@/lib/telemetry";
import { useLexicon } from "@/lib/lexicon";
import { metricDef } from "@/lib/metricDefs";
import MetricInfo from "./MetricInfo";
import PanelInfo from "./PanelInfo";
import { PanelSubtitle } from "./Lex";

interface RingDef {
  key: string;
  label: string;
  value: number;
  hint: string;
}

// How many extra signals show before the "+N more" expander (Fix 6: the old
// panel silently truncated to the FIRST four in arbitrary object-key order).
const EXTRAS_VISIBLE = 6;

export default function ControlSignalRings({ affect }: { affect: Affect }) {
  const [expanded, setExpanded] = useState(false);
  const [infoKey, setInfoKey] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Close an open info popover on outside click (same pattern as MetricsStrip).
  useEffect(() => {
    if (!infoKey) return;
    const onDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setInfoKey(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [infoKey]);

  const { t, tip } = useLexicon();
  const rings: RingDef[] = [
    { key: "valence", label: t("valence_label"), value: affect.valence, hint: t("valence_hint") },
    { key: "arousal", label: t("arousal_label"), value: affect.arousal, hint: t("arousal_hint") },
    { key: "homeostasis", label: t("homeostasis_label"), value: affect.homeostasis, hint: t("homeostasis_hint") },
  ];

  // ALL extra signals, sorted by intensity — not the first four in arbitrary
  // object order. The expander reveals the full affect vector.
  const extras = useMemo(
    () => Object.entries(affect.extra || {}).sort((a, b) => b[1] - a[1]),
    [affect.extra],
  );
  const shown = expanded ? extras : extras.slice(0, EXTRAS_VISIBLE);
  const hidden = extras.length - EXTRAS_VISIBLE;

  return (
    <Card id="box-affect" className="h-full">
      <CardHeader className="pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <span title={tip("affect_title")}>{t("affect_title")}</span>
          <PanelInfo
            title="Control-signal state"
            perspective="in-attention"
            what="The current internal signal state: the three core rings (reward sign − ↔ +, activation level, and how close the whole signal vector sits to its setpoints) plus every extra signal currently active, sorted by intensity. Each value is a 0–100 normalized level; the ℹ️ on any signal explains it down to the code that computes it."
            source="affect_state via the telemetry socket (emitter: brain/ORRIN_loop.py _emit_affect)"
            good="Signals that breathe — moving with events and decaying back toward their setpoints — rather than pinned at 0 or 100."
            src={{ file: "brain/ORRIN_loop.py", start: 170, end: 222, label: "_emit_affect" }}
          />
          <PanelSubtitle id="affect_sub" />
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4" ref={rootRef}>
        <div className="grid grid-cols-3 gap-2">
          {rings.map((r) => (
            <Ring
              key={r.key}
              label={r.label}
              value={r.value}
              hint={r.hint}
              infoOpen={infoKey === r.key}
              onInfo={metricDef(r.key) ? () => setInfoKey((k) => (k === r.key ? null : r.key)) : undefined}
              infoKey={r.key}
              onCloseInfo={() => setInfoKey(null)}
            />
          ))}
        </div>
        {extras.length > 0 && (
          <div className="border-t pt-3">
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {shown.map(([k, v]) => (
                <Bar
                  key={k}
                  signal={k}
                  value={v}
                  infoOpen={infoKey === k}
                  onInfo={metricDef(k) ? () => setInfoKey((cur) => (cur === k ? null : k)) : undefined}
                  onCloseInfo={() => setInfoKey(null)}
                />
              ))}
            </div>
            {hidden > 0 && (
              <button
                onClick={() => setExpanded((v) => !v)}
                className="mt-2 flex items-center gap-1 text-[10px] font-medium text-muted-foreground hover:text-foreground"
              >
                <ChevronDown className={`h-3 w-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
                {expanded ? "Show fewer" : `+${hidden} more signal${hidden > 1 ? "s" : ""}`}
              </button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Ring({
  label,
  value,
  hint,
  infoOpen,
  onInfo,
  infoKey,
  onCloseInfo,
}: Omit<RingDef, "key"> & { infoOpen?: boolean; onInfo?: () => void; infoKey: string; onCloseInfo: () => void }) {
  const size = 92;
  const stroke = 8;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = Math.max(0, Math.min(1, value));
  const dash = c * pct;
  const color = ringColor(infoKey, pct);
  const def = metricDef(infoKey);

  return (
    <div className="relative flex flex-col items-center gap-1.5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="hsl(var(--secondary))" strokeWidth={stroke} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${c}`}
            style={{ transition: "stroke-dasharray 0.6s ease, stroke 0.6s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-lg font-semibold tabular-nums">{Math.round(pct * 100)}</span>
          <span className="text-[9px] uppercase tracking-wider text-muted-foreground">/ 100</span>
        </div>
      </div>
      <div className="text-center">
        <div className="flex items-center justify-center gap-0.5 text-xs font-medium">
          {label}
          {onInfo && (
            <button onClick={onInfo} className="rounded p-0.5 text-muted-foreground/50 hover:text-foreground" aria-label={`What is ${label}?`}>
              <Info className="h-3 w-3" />
            </button>
          )}
        </div>
        <div className="text-[10px] text-muted-foreground">{hint}</div>
      </div>
      {infoOpen && def && (
        <MetricInfo m={def} onClose={onCloseInfo} className="absolute left-1/2 top-full z-30 max-h-[55vh] w-80 -translate-x-1/2 overflow-auto rounded-lg border border-border bg-popover p-3 text-left shadow-2xl" />
      )}
    </div>
  );
}

function Bar({
  signal,
  value,
  infoOpen,
  onInfo,
  onCloseInfo,
}: {
  signal: string;
  value: number;
  infoOpen?: boolean;
  onInfo?: () => void;
  onCloseInfo: () => void;
}) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const def = metricDef(signal);
  return (
    <div className="relative">
      <div className="mb-1 flex items-center justify-between text-[11px]">
        <span className="flex items-center gap-0.5 capitalize text-muted-foreground">
          {signal.replace(/_/g, " ")}
          {onInfo && (
            <button onClick={onInfo} className="rounded p-0.5 text-muted-foreground/40 hover:text-foreground" aria-label={`What is ${signal}?`}>
              <Info className="h-2.5 w-2.5" />
            </button>
          )}
        </span>
        <span className="tabular-nums">{pct}%</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
        <div
          className="h-full rounded-full bg-signal-accent transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>
      {infoOpen && def && (
        <MetricInfo m={def} onClose={onCloseInfo} className="absolute left-0 top-7 z-30 max-h-[55vh] w-80 overflow-auto rounded-lg border border-border bg-popover p-3 text-left shadow-2xl" />
      )}
    </div>
  );
}

// Keyed by the signal KEY, not the display label — labels are lexicon-translated
// (Fix 12) and must never carry behavior.
function ringColor(key: string, pct: number) {
  if (key === "homeostasis") {
    return pct > 0.66 ? "hsl(var(--signal-ok))" : pct > 0.4 ? "hsl(var(--signal-warn))" : "hsl(var(--signal-error))";
  }
  if (key === "valence") {
    return pct > 0.55 ? "hsl(var(--signal-ok))" : pct < 0.4 ? "hsl(var(--signal-error))" : "hsl(var(--signal-info))";
  }
  return "hsl(var(--signal-accent))"; // arousal
}
