import { Brain } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { usePolledJSON } from "@/lib/usePolled";

// Learning page §5.1 (unwired-telemetry 3A): surfaces llm_gate.gate_report's
// 7-day symbolic-intelligence roll-up — "is it actually getting smarter?". The
// data is a read-only projection of brain/data/symbolic_progress.json served by
// GET /api/intelligence (the report function itself flushes live counters, which
// the backend process doesn't have, so the endpoint re-aggregates the persisted
// day rows instead). Honest-empty until the first dream cycle writes a row.

interface DayRow {
  date?: string;
  symbolic_hits?: number;
  llm_calls?: number;
  symbolic_ratio?: number;
  rules_total?: number;
}
interface Intelligence {
  summary?: string;
  days?: DayRow[];
  overall_ratio?: number;
  rules_start?: number;
  rules_end?: number;
  rules_growth?: number;
  experiments_run?: number;
  experiments_succeeded?: number;
  sub_goals_spawned?: number;
  conflicts_detected?: number;
  concept_depth?: number;
  causal_density?: number;
  goal_completion_rate?: number;
}

function pct(n?: number): string {
  return `${Math.round((Number(n) || 0) * 100)}%`;
}

export default function IntelligenceGrowthPanel() {
  const data = usePolledJSON<Intelligence>("/api/intelligence?days=7", 30_000);
  const days = data?.days ?? [];
  const ratio = Number(data?.overall_ratio ?? 0);
  const growth = Number(data?.rules_growth ?? 0);
  const maxRules = Math.max(1, ...days.map((d) => Number(d.rules_total ?? 0)));

  const stats: Array<[string, string]> = [
    ["Rules", `${data?.rules_start ?? 0} → ${data?.rules_end ?? 0}`],
    ["Experiments", `${data?.experiments_succeeded ?? 0}/${data?.experiments_run ?? 0}`],
    ["Sub-goals spawned", `${data?.sub_goals_spawned ?? 0}`],
    ["Conflicts detected", `${data?.conflicts_detected ?? 0}`],
    ["Concept depth", (Number(data?.concept_depth ?? 0)).toFixed(2)],
    ["Causal density", (Number(data?.causal_density ?? 0)).toFixed(3)],
    ["Goal completion", pct(data?.goal_completion_rate)],
  ];

  return (
    <section className="space-y-3 border-t pt-5">
      <div className="space-y-1">
        <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
          <Brain className="h-4 w-4 text-primary" />
          Is it getting smarter?
        </h2>
        <p className="text-sm text-muted-foreground">
          The 7-day symbolic-intelligence roll-up: how much of its thinking it
          resolved on its own (without the LLM), and how its rule base, experiments,
          and world model grew.
        </p>
      </div>

      {days.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            {data == null
              ? "Loading…"
              : "No symbolic-progress data yet — the first snapshot is written during a dream cycle."}
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="space-y-4 py-4">
            <div>
              <div className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>Resolved without the LLM (7-day)</span>
                <span className="tabular-nums text-foreground">{pct(ratio)}</span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-secondary">
                <div className="h-full rounded-full bg-signal-ok" style={{ width: `${Math.max(0, Math.min(100, ratio * 100))}%` }} />
              </div>
            </div>

            <div className="flex items-end gap-1" title="Rule base per day">
              {days.map((d, i) => (
                <div key={`${d.date ?? ""}-${i}`} className="flex flex-1 flex-col items-center gap-1">
                  <div className="flex h-16 w-full items-end">
                    <div
                      className="w-full rounded-t bg-primary/70"
                      style={{ height: `${Math.max(4, (Number(d.rules_total ?? 0) / maxRules) * 100)}%` }}
                    />
                  </div>
                  <span className="text-[9px] tabular-nums text-muted-foreground">{(d.date ?? "").slice(5)}</span>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 sm:grid-cols-3">
              {stats.map(([label, value]) => (
                <div key={label} className="flex items-baseline justify-between gap-2 text-xs">
                  <span className="text-muted-foreground">{label}</span>
                  <span className="tabular-nums text-foreground">{value}</span>
                </div>
              ))}
            </div>

            <p className="text-xs leading-relaxed text-muted-foreground">
              Rule base moved {growth >= 0 ? "+" : ""}
              <span className={growth >= 0 ? "text-signal-ok" : "text-signal-error"}>{growth}</span> over the window.
            </p>
          </CardContent>
        </Card>
      )}
    </section>
  );
}
