import { BatteryCharging } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { MiniBars } from "./viz";

/** Box ⑤ — Drives & body / interoception. The allostatic resource story:
 *  motivation drives, energy mode, body vitals, and the live interoceptive
 *  cost model (what each function is EXPECTED to cost vs. what it last cost —
 *  the gap is "strain"). The live per-act stream also rides telemetry now
 *  (Fix 7 forwarded `interoception`); these files are the history behind it. */

interface IoRow { fn: string; ema?: number; last?: number; n?: number }

/** The live per-act interoception block the loop emits after every executed
 *  function (Fix 7 forwards it; this panel now binds its "now" view to it
 *  instead of being poll-only — the ui_fixes.md box-⑤ note). */
export interface LiveIntero {
  fn?: string;
  predicted_ms?: number;
  actual_ms?: number;
  pe_ms?: number;
  energy?: number;
  resource_deficit?: number;
  allostatic_load?: number;
  [k: string]: unknown;
}

export default function DemandsPanel({ live }: { live?: LiveIntero | null }) {
  const data = usePoll<{
    drives?: Record<string, number>;
    energy?: { mode?: string; level?: number };
    body?: { body_states?: string[]; vitals?: { rss_mb?: number; cpu_util?: number }; dominant?: string };
    interoception?: IoRow[];
  }>(`${API}/demands`, 15_000);
  const drives = Object.entries(data?.drives || {}).sort((a, b) => b[1] - a[1]);
  const io = (data?.interoception || []).slice(0, 8);
  const maxCost = Math.max(1, ...io.map((r) => Math.max(r.ema || 0, r.last || 0)));

  return (
    <Card id="box-drives" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <BatteryCharging className="h-4 w-4" /> <LexText id="drives_title" />
          <PanelInfo
            title="Priority weights & resource self-monitoring"
            perspective="agent-accessible"
            what="Its demand-pressure accumulators (what it is weighting right now), the current resource-cadence mode, real host resource readings (memory, CPU), and the resource cost model: the learned expected cost of each cognitive function vs. what it actually cost last time — sustained gaps surface as cost pressure."
            source="brain/data/motivation_state.json · energy_mode.json · resource_self_monitor.json · cost_prediction_model.json"
            good="Priority weights that MOVE over time (a flatlined 1.0 means depletion isn't biting), and expected≈actual cost — big persistent gaps mean its cost self-model is off."
            src={{ file: "brain/cognition/cost_prediction.py", start: 1, end: 70, label: "cost model (interoception wire field)" }}
          />
          <PanelSubtitle id="drives_sub" />
          <StaleBadge url={`${API}/demands`} pollMs={15_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">
          energy: {data?.energy?.mode ?? "—"}
          {data?.body?.dominant ? ` · state ${data.body.dominant}` : ""}
        </span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {/* "Now" — the live per-act interoception frame off the socket, not a poll. */}
        {live && live.fn && (
          <div
            className="rounded-lg border border-border bg-card/60 px-3 py-2"
            title="Live from the telemetry socket: the resource read of the function that just ran (predicted vs actual cost; the gap surfaces as cost pressure)."
          >
            <div className="flex items-center gap-1.5">
              <span className="inline-flex h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-signal-ok" />
              <span className="truncate font-mono text-[11px] text-foreground/85">{live.fn}</span>
              <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">
                {Number(live.predicted_ms ?? 0).toFixed(0)} → {Number(live.actual_ms ?? 0).toFixed(0)} ms
              </span>
            </div>
            <div className="mt-1 flex gap-3 text-[9.5px] text-muted-foreground">
              {live.energy != null && <span>energy {Math.round(Number(live.energy) * 100)}%</span>}
              {live.resource_deficit != null && <span>fatigue {Number(live.resource_deficit).toFixed(3)}</span>}
              {live.allostatic_load != null && <span>allostatic load {Number(live.allostatic_load).toFixed(3)}</span>}
              {live.pe_ms != null && <span className="ml-auto">surprise {Number(live.pe_ms).toFixed(1)} ms</span>}
            </div>
          </div>
        )}

        {drives.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Drives</div>
            <MiniBars
              rows={drives.map(([k, v]) => ({ label: k.replace(/_/g, " "), value: Number(v) }))}
              color="hsl(var(--signal-accent))"
            />
          </div>
        )}

        {io.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground" title="Expected (learned EMA) vs last actual cost, ms — the gap is cost pressure">
              Interoceptive cost · expected vs last (ms)
            </div>
            <div className="space-y-1">
              {io.map((r) => {
                const strained = (r.last || 0) > (r.ema || 0) * 1.5;
                return (
                  <div key={r.fn} title={`${r.n ?? 0} observations`}>
                    <div className="mb-0.5 flex justify-between text-[10px]">
                      <span className="truncate font-mono text-muted-foreground">{r.fn}</span>
                      <span className="tabular-nums" style={{ color: strained ? "hsl(var(--signal-warn))" : "hsl(var(--foreground) / 0.8)" }}>
                        {Number(r.ema ?? 0).toFixed(1)} → {Number(r.last ?? 0).toFixed(1)}{strained ? " ⚠" : ""}
                      </span>
                    </div>
                    <div className="relative h-1.5 overflow-hidden rounded-full bg-secondary">
                      <div className="absolute h-full rounded-full bg-signal-info/50" style={{ width: `${((r.ema || 0) / maxCost) * 100}%` }} />
                      <div
                        className="absolute h-full w-0.5"
                        style={{ left: `${((r.last || 0) / maxCost) * 100}%`, background: strained ? "hsl(var(--signal-warn))" : "hsl(var(--foreground) / 0.7)" }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {data?.body?.vitals && (
          <div className="border-t border-border/60 pt-2 text-[10px] text-muted-foreground">
            body: {(data.body.body_states || []).join(", ") || "—"} · RSS {Math.round(Number(data.body.vitals.rss_mb ?? 0))} MB · CPU {Math.round(Number(data.body.vitals.cpu_util ?? 0) * 100)}%
          </div>
        )}
      </CardContent>
    </Card>
  );
}
