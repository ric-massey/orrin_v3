import { Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { Gauge, Sparkline, StackedFlow } from "./viz";

/** Box ② — Goal closure / outcomes. The closure-remediation story: does the
 *  goal population stay bounded, and HOW do goals actually close. Persisted
 *  daily to outcome_metrics.json; was invisible. Pairs with B1. */

interface Outcome {
  date?: string;
  active_goals?: number;
  average_goal_age?: number;
  goals_completed?: number;
  goals_failed?: number;
  goals_retired?: number;
  satiety_closures?: number;
  abandonment_closures?: number;
  completion_rate?: number;
  abandonment_rate?: number;
  [k: string]: unknown;
}

function fmtAge(seconds?: number): string {
  if (!seconds || seconds <= 0) return "—";
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
  if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
  return `${(seconds / 86400).toFixed(1)}d`;
}

export default function GoalHealthPanel() {
  const data = usePoll<{ history?: Outcome[]; latest?: Outcome | null }>(`${API}/outcomes`, 30_000);
  const latest = data?.latest;
  const history = data?.history || [];

  return (
    <Card id="box-goals" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <Target className="h-4 w-4" /> <LexText id="goalhealth_title" />
          <PanelInfo
            title="Goal closure / outcomes"
            perspective="dev-only"
            what="Daily metrics on how the goal population behaves: how many are active, how often they complete vs. get abandoned, and which closure path ended them (completed / retired / satiety / abandoned)."
            source="brain/data/outcome_metrics.json (writer: brain/cognition/planning/outcome_metrics.py)"
            good="Active goals PLATEAU over the rolling window (ties to B1 — bounded, not accumulating), completion rate well above abandonment."
            src={{ file: "brain/cognition/planning/outcome_metrics.py", start: 1, end: 70, label: "outcome_metrics" }}
          />
          <PanelSubtitle id="goalhealth_sub" />
          <StaleBadge url={`${API}/outcomes`} pollMs={30_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{latest?.date ?? "—"}</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {!latest ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No outcome metrics recorded yet (written daily).</div>
        ) : (
          <>
            <div className="flex items-center justify-around gap-2">
              <div className="text-center">
                <div className="text-xl font-semibold tabular-nums">{latest.active_goals ?? "—"}</div>
                <div className="text-[9px] uppercase tracking-wide text-muted-foreground">active</div>
              </div>
              <Gauge value={Number(latest.completion_rate ?? 0)} label="completion" color="hsl(var(--signal-ok))" />
              <Gauge value={Number(latest.abandonment_rate ?? 0)} label="abandon" color="hsl(var(--signal-error))" />
              <div className="text-center">
                <div className="text-xl font-semibold tabular-nums">{fmtAge(Number(latest.average_goal_age))}</div>
                <div className="text-[9px] uppercase tracking-wide text-muted-foreground">avg age</div>
              </div>
            </div>

            <div>
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">How goals closed</div>
              <StackedFlow
                parts={[
                  { label: "completed", value: Number(latest.goals_completed ?? 0), color: "hsl(var(--signal-ok))" },
                  { label: "retired", value: Number(latest.goals_retired ?? 0), color: "hsl(var(--signal-info))" },
                  { label: "satiety", value: Number(latest.satiety_closures ?? 0), color: "hsl(var(--signal-accent))" },
                  { label: "abandoned", value: Number(latest.abandonment_closures ?? 0), color: "hsl(var(--signal-error))" },
                  { label: "failed", value: Number(latest.goals_failed ?? 0), color: "hsl(var(--signal-warn))" },
                ]}
              />
            </div>

            {history.length > 1 ? (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
                  Active goals over {history.length} days — should plateau (B1)
                </div>
                <Sparkline points={history.map((h) => Number(h.active_goals ?? 0))} width={220} height={32} min={0} />
              </div>
            ) : (
              <div className="text-[10px] text-muted-foreground/70">
                One day of data so far — the plateau story needs a few more days of history.
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
