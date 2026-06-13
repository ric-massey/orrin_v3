import { useEffect, useMemo, useRef, useState } from "react";
import { Area, AreaChart, LabelList, ResponsiveContainer, Tooltip, YAxis } from "recharts";
import { Check, ChevronDown, Hash, Info } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TelemetryState } from "@/lib/telemetry";
import { useLocalStorage } from "@/lib/useLocalStorage";

import { METRICS } from "@/lib/metricDefs";
import MetricInfo from "./MetricInfo";
import PanelInfo from "./PanelInfo";
import { PanelSubtitle } from "./Lex";

const DEFAULT_KEYS = ["valence", "arousal", "homeostasis"];
const SEL_KEY = "orrin.metrics.selected";
const VAL_KEY = "orrin.metrics.showValues";

const pct = (v: number | undefined | null) => (typeof v === "number" ? Math.round(v * 100) : null);

/** Keep only known metric keys; fall back to defaults when empty/invalid.
 *  Migrates legacy values transparently via the shared useLocalStorage hook. */
function sanitizeSelected(raw: unknown): string[] {
  if (Array.isArray(raw)) {
    const valid = raw.filter(
      (k): k is string => typeof k === "string" && METRICS.some((m) => m.key === k),
    );
    if (valid.length) return valid;
  }
  return DEFAULT_KEYS;
}

export default function MetricsStrip({ telemetry }: { telemetry: TelemetryState }) {
  // Persisted preferences now route through the shared, private-mode-safe hook (M4).
  // `showValues` coerces the legacy "1"/"0" representation via sanitize → boolean.
  const [selected, setSelected] = useLocalStorage<string[]>(SEL_KEY, DEFAULT_KEYS, { sanitize: sanitizeSelected });
  const [open, setOpen] = useState(false);
  const [showValues, setShowValues] = useLocalStorage<boolean>(VAL_KEY, false, { sanitize: (r) => !!r });
  const [infoKey, setInfoKey] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const legendRef = useRef<HTMLDivElement>(null);

  // Close the picker on outside click.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  // Close an open info popover on outside click.
  useEffect(() => {
    if (!infoKey) return;
    const onDown = (e: MouseEvent) => {
      if (legendRef.current && !legendRef.current.contains(e.target as Node)) setInfoKey(null);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [infoKey]);

  const data = telemetry.metricSeries.slice(-120);
  const latest = data.length ? data[data.length - 1] : undefined;
  const active = useMemo(() => METRICS.filter((m) => selected.includes(m.key)), [selected]);

  // Per-series index of the LAST defined point. With `connectNulls` and sparse
  // series (a metric missing in early history), the rendered last point for a
  // line may not be at `data.length - 1`, which made its end-label vanish (M1).
  const lastDefinedIndex = useMemo(() => {
    const idx: Record<string, number> = {};
    for (const m of active) {
      let last = -1;
      for (let i = 0; i < data.length; i++) {
        const v = (data[i] as Record<string, unknown>)?.[m.key];
        if (v != null) last = i;
      }
      idx[m.key] = last;
    }
    return idx;
  }, [data, active]);

  const toggle = (key: string) =>
    setSelected((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]));

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          System Metrics
          <PanelInfo
            title="System Metrics"
            what="Any of his signals charted over time on one 0–100 scale — pick which series to show with the Metrics button. History is replayed from the server on connect, so the chart is continuous across restarts."
            source="metric series via the telemetry socket (history persisted in brain/data/telemetry_history.json)"
            good="Pick three or four related signals and watch how they interact — e.g. fatigue climbing while motivation decays toward its setpoint."
          />
          <PanelSubtitle id="metrics_sub" />
        </CardTitle>

        <div className="flex items-center gap-2">
          {/* Values toggle — show the current 0–100 level on each legend chip. */}
          <button
            type="button"
            onClick={() => setShowValues((v) => !v)}
            title="Show current values (0–100)"
            className={`flex items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium transition-colors ${
              showValues
                ? "border-transparent bg-foreground/10 text-foreground"
                : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground"
            }`}
          >
            <Hash className="h-3.5 w-3.5" />
            Values
          </button>

          {/* Metric picker. */}
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setOpen((o) => !o)}
              className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              Metrics
              <span className="text-foreground/70">({active.length})</span>
              <ChevronDown className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-180" : ""}`} />
            </button>

            {open && (
              <div className="absolute right-0 z-20 mt-1.5 w-64 overflow-hidden rounded-lg border border-border bg-popover shadow-lg">
                <div className="border-b border-border px-3 py-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Show on chart · scale 0–100
                </div>
                <div className="max-h-72 overflow-y-auto py-1">
                  {METRICS.map((m) => {
                    const on = selected.includes(m.key);
                    return (
                      <button
                        key={m.key}
                        type="button"
                        onClick={() => toggle(m.key)}
                        className="group flex w-full items-start gap-2.5 px-3 py-1.5 text-left transition-colors hover:bg-muted"
                      >
                        <span
                          className={`mt-0.5 flex h-4 w-4 flex-none items-center justify-center rounded border transition-colors ${
                            on ? "border-transparent" : "border-border"
                          }`}
                          style={on ? { background: m.color } : undefined}
                        >
                          {on && <Check className="h-3 w-3 text-white" />}
                        </span>
                        <span className="min-w-0">
                          <span className="flex items-center gap-1.5 text-xs font-medium text-foreground">
                            <span className="h-2 w-2 flex-none rounded-full" style={{ background: m.color }} />
                            {m.label}
                          </span>
                          <span className="mt-0.5 block text-[10px] leading-snug text-muted-foreground">{m.desc}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
                {/* M5: a clean way out of a buried configuration. */}
                <div className="border-t border-border px-3 py-2">
                  <button
                    type="button"
                    onClick={() => {
                      setSelected(DEFAULT_KEYS);
                      setShowValues(false);
                    }}
                    className="text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
                  >
                    Reset to defaults
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {/* Legend — selected series, each with a live value (toggle) + a working info popover. */}
        <div ref={legendRef} className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {active.length === 0 && (
            <span className="text-[11px] text-muted-foreground">No metrics selected — open “Metrics”.</span>
          )}
          {active.map((m) => {
            const val = pct(latest?.[m.key]);
            return (
              <span key={m.key} className="relative flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <span className="h-2 w-2 rounded-full" style={{ background: m.color }} />
                <span className="text-foreground/90">{m.label}</span>
                {showValues && val !== null && (
                  <span className="font-mono tabular-nums font-semibold" style={{ color: m.color }}>
                    {val}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => setInfoKey((k) => (k === m.key ? null : m.key))}
                  className="rounded p-0.5 text-muted-foreground/60 transition-colors hover:bg-muted hover:text-foreground"
                  aria-label={`What is ${m.label}?`}
                >
                  <Info className="h-3 w-3" />
                </button>

                {infoKey === m.key && <MetricInfo m={m} onClose={() => setInfoKey(null)} />}
              </span>
            );
          })}
        </div>

        <div className="h-[140px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data} margin={{ top: 4, right: 64, bottom: 0, left: -22 }}>
              <defs>
                {active.map((m) => (
                  <linearGradient key={m.key} id={`g-${m.key}`} x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={m.color} stopOpacity={0.3} />
                    <stop offset="100%" stopColor={m.color} stopOpacity={0} />
                  </linearGradient>
                ))}
              </defs>
              {/* Axis on the same 0–100 unit as the values + tooltip. */}
              <YAxis
                domain={[0, 1]}
                ticks={[0, 0.5, 1]}
                tickFormatter={(v: number) => `${Math.round(v * 100)}`}
                tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                tickLine={false}
                axisLine={false}
                width={30}
              />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--popover))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 11,
                }}
                labelFormatter={() => ""}
                formatter={(v: number, key: string) => {
                  const def = METRICS.find((m) => m.key === key);
                  return [`${Math.round(Number(v) * 100)}`, def?.label ?? key];
                }}
              />
              {active.map((m) => (
                <Area
                  key={m.key}
                  type="monotone"
                  dataKey={m.key}
                  stroke={m.color}
                  strokeWidth={1.8}
                  fill={`url(#g-${m.key})`}
                  isAnimationActive={false}
                  dot={false}
                  connectNulls
                >
                  {/* End-of-line tag: the metric's name (and value, when Values is on)
                      sits at the right end of its own line, color-matched — so every
                      line is unmistakably identified without reading the legend. */}
                  <LabelList
                    dataKey={m.key}
                    content={(p: any) => {
                      if (p.index !== lastDefinedIndex[m.key] || p.value == null) return null;
                      const txt = showValues ? `${m.label} ${Math.round(p.value * 100)}` : m.label;
                      return (
                        <text
                          x={p.x + 8}
                          y={p.y}
                          dy={3.5}
                          fontSize={10}
                          fontWeight={600}
                          fill={m.color}
                        >
                          {txt}
                        </text>
                      );
                    }}
                  />
                </Area>
              ))}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
