import { Crosshair } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { HitMissStrip, MiniBars, Sparkline } from "./viz";

/** Box ④ — Predictions & surprise (active inference). Makes the "minimize
 *  surprise" loop visible: recent predictions vs outcomes, per-domain accuracy,
 *  and the Brier score — a single, defensible "how well-calibrated is it"
 *  number that nothing displayed (live: brier 0.0099 over n=758). */

interface Prediction {
  prediction?: string;
  confidence?: number;
  status?: string;     // pending | evaluated
  outcome?: string;    // correct | incorrect
  resolved?: boolean;
  domain?: string;
  basis?: string;
  created_ts?: string;
}
interface TrendPoint { brier?: number; exploration_ratio?: number; n?: number; timestamp?: string | number }
interface ExplorationSummary {
  explore?: number;
  exploit?: number;
  ratio?: number | null;
  trend?: TrendPoint[];
}

export default function PredictionsPanel() {
  const data = usePoll<{
    calibration?: { brier?: number; bias?: number; n?: number };
    calibration_trend?: TrendPoint[];
    exploration?: ExplorationSummary;
    domains?: Record<string, { accuracy?: number; total?: number; correct?: number }>;
    recent?: Prediction[];
    total?: number;
  }>(`${API}/predictions?n=40`, 15_000);
  const cal = data?.calibration;
  const calibrationTrend = data?.calibration_trend || [];
  const exploration = data?.exploration;
  const explorationTrend = exploration?.trend || [];
  const lastCalibrationTrend = calibrationTrend[calibrationTrend.length - 1];
  const recent = data?.recent || [];
  const resolved = recent.filter((p) => p.resolved || p.status === "evaluated");
  const hits = resolved.map((p) => (p.outcome ? p.outcome === "correct" : null));
  const pending = recent.filter((p) => !p.resolved && p.status !== "evaluated");
  const domains = Object.entries(data?.domains || {});

  return (
    <Card id="box-predictions" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Crosshair className="h-4 w-4" /> <LexText id="predictions_title" />
          <PanelInfo
            title="Predictions & surprise"
            perspective="agent-accessible"
            what="It commits to falsifiable expectations about what its actions will do ('after look_outward, risk_estimate falls'), then checks them. This box shows the recent hit/miss record, per-domain accuracy, and the Brier score — the standard calibration measure (0 = perfectly calibrated, 0.25 = coin-flip confidence)."
            source="brain/data/predictions.json · prediction_domain_stats.json · calibration_state.json"
            good="Brier well under 0.1 with a meaningful n, and a hit strip that's mostly green. Confirmed predictions crystallize into symbolic rules."
            src={{ file: "brain/cognition/prediction.py", start: 365, end: 430, label: "check_predictions" }}
          />
          <PanelSubtitle id="predictions_sub" />
          <StaleBadge url={`${API}/predictions`} pollMs={15_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{data?.total ?? "—"} total · {pending.length} pending</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {cal?.n ? (
          <div className="flex items-center gap-4 rounded-lg border border-border bg-card/60 px-3 py-2">
            <div className="text-center">
              <div className="text-xl font-semibold tabular-nums" style={{ color: Number(cal.brier) < 0.1 ? "hsl(var(--signal-ok))" : Number(cal.brier) < 0.25 ? "hsl(var(--signal-warn))" : "hsl(var(--signal-error))" }}>
                {Number(cal.brier ?? 0).toFixed(4)}
              </div>
              <div className="text-[9px] uppercase tracking-wide text-muted-foreground">Brier score</div>
            </div>
            <div className="text-[10px] leading-snug text-muted-foreground">
              over n={cal.n} resolved predictions · bias {Number(cal.bias ?? 0).toFixed(3)}
              <span className="block text-muted-foreground/70">0 = perfectly calibrated · 0.25 = coin flip</span>
            </div>
          </div>
        ) : (
          <div className="py-4 text-center text-xs text-muted-foreground">No calibration data yet.</div>
        )}

        {(calibrationTrend.length > 1 || explorationTrend.length > 1) && (
          <div className="grid gap-2 sm:grid-cols-2">
            {calibrationTrend.length > 1 && (
              <div className="rounded-lg border border-border bg-card/50 px-3 py-2">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Calibration trend</span>
                  <span className="text-[9px] tabular-nums text-muted-foreground">rolling {lastCalibrationTrend?.n ?? 0}</span>
                </div>
                <Sparkline points={calibrationTrend.map((p) => Number(p.brier ?? 0))} width={220} height={30} min={0} max={0.35} color="hsl(var(--signal-info))" />
              </div>
            )}
            {explorationTrend.length > 1 && (
              <div className="rounded-lg border border-border bg-card/50 px-3 py-2">
                <div className="mb-1 flex items-center justify-between gap-2">
                  <span className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Novelty / exploit</span>
                  <span className="text-[9px] tabular-nums text-muted-foreground">
                    {exploration?.explore ?? 0} explore · {exploration?.exploit ?? 0} exploit
                  </span>
                </div>
                <Sparkline points={explorationTrend.map((p) => Number(p.exploration_ratio ?? 0))} width={220} height={30} min={0} max={1} color="hsl(var(--signal-ok))" />
                <div className="mt-1 text-[9px] text-muted-foreground">
                  recent explore ratio {exploration?.ratio == null ? "—" : `${Math.round(Number(exploration.ratio) * 100)}%`}
                </div>
              </div>
            )}
          </div>
        )}

        {hits.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              Recent resolved ({hits.filter(Boolean).length}/{hits.length} correct)
            </div>
            <HitMissStrip results={hits} title="green = prediction came true, red = missed (oldest → newest)" />
          </div>
        )}

        {domains.length > 0 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Accuracy by domain</div>
            <MiniBars
              rows={domains.map(([d, s]) => ({
                label: d.toLowerCase(),
                value: Number(s.accuracy ?? 0),
                title: `${s.correct ?? 0} / ${s.total ?? 0} correct`,
              }))}
              color="hsl(var(--signal-info))"
            />
          </div>
        )}

        <div>
          <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Latest predictions</div>
          <div className="space-y-1">
            {[...recent].reverse().slice(0, 8).map((p, i) => (
              <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1 text-[10px]">
                <div className="truncate leading-snug text-foreground/85" title={p.prediction}>{p.prediction}</div>
                <div className="mt-0.5 flex gap-2 text-[9px] text-muted-foreground">
                  <span>conf {(Number(p.confidence ?? 0)).toFixed(2)}</span>
                  {p.domain && <span>{p.domain.toLowerCase()}</span>}
                  {p.basis && <span>{p.basis}</span>}
                  <span
                    className="ml-auto font-semibold"
                    style={{ color: p.outcome === "correct" ? "hsl(var(--signal-ok))" : p.outcome === "incorrect" ? "hsl(var(--signal-error))" : "hsl(var(--muted-foreground))" }}
                  >
                    {p.outcome || p.status || "pending"}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
