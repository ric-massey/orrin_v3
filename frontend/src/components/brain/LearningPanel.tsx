import { TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import { LexText, PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { Sparkline } from "./viz";

/** Box ⑥ — Learning / reward. How he learns which thoughts pay off: per-
 *  function bandit stats (which cognition is "working"), suppressions, and the
 *  recent reward trace — the core adaptive loop. */

interface FnRow { fn: string; count: number; avg_reward: number }
interface RewardEvent { actual_reward?: number; expected_reward?: number; timestamp?: string; source?: string }

const rewardColor = (r: number) =>
  r >= 0.5 ? "hsl(var(--signal-ok))" : r >= 0.3 ? "hsl(var(--signal-warn))" : "hsl(var(--signal-error))";

export default function LearningPanel() {
  const data = usePoll<{
    functions?: FnRow[];
    suppressed?: Record<string, unknown>;
    reward_trace?: RewardEvent[];
  }>(`${API}/learning?n=10`, 20_000);
  const fns = data?.functions || [];
  const maxCount = Math.max(1, ...fns.map((f) => f.count));
  const trace = data?.reward_trace || [];
  const suppressed = Object.keys(data?.suppressed || {});

  return (
    <Card id="box-learning" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
          <TrendingUp className="h-4 w-4" /> <LexText id="learning_title" />
          <PanelInfo
            title="Learning / reward"
            perspective="agent-accessible"
            what="The bandit's view of his own cognition: how often each function gets picked, the average reward it has earned (is it 'working'?), which functions are currently suppressed for underperforming, and the raw reward events as they land."
            source="brain/data/decision_stats.json · bandit_state.json · reward_trace.json"
            good="A spread of rewards (not everything pinned at one value), heavy use concentrated on functions that actually earn it, and suppressions that come AND go."
            src={{ file: "brain/think/think_utils/finalize.py", start: 460, end: 500, label: "decision recording" }}
          />
          <PanelSubtitle id="learning_sub" />
          <StaleBadge url={`${API}/learning`} pollMs={20_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{fns.length} tracked</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {fns.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No decision stats yet.</div>
        ) : (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              Top functions · bar = usage, number = avg reward
            </div>
            <div className="space-y-1">
              {fns.map((f) => (
                <div key={f.fn}>
                  <div className="mb-0.5 flex justify-between text-[10px]">
                    <span className="truncate font-mono text-muted-foreground">{f.fn}</span>
                    <span className="tabular-nums">
                      <span className="text-muted-foreground/70">{f.count}× · </span>
                      <span style={{ color: rewardColor(f.avg_reward) }}>{f.avg_reward.toFixed(2)}</span>
                    </span>
                  </div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                    <div className="h-full rounded-full" style={{ width: `${(f.count / maxCount) * 100}%`, background: rewardColor(f.avg_reward) }} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {trace.length > 1 && (
          <div>
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              Reward trace (last {trace.length})
            </div>
            <Sparkline points={trace.map((t) => Number(t.actual_reward ?? 0))} width={220} height={30} min={0} max={1} color="hsl(var(--signal-ok))" />
          </div>
        )}

        {suppressed.length > 0 && (
          <div className="border-t border-border/60 pt-2">
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Currently suppressed (underperforming)</div>
            <div className="flex flex-wrap gap-1">
              {suppressed.map((s) => (
                <span key={s} className="rounded bg-signal-error/10 px-1.5 py-0.5 font-mono text-[9px] text-signal-error">{s}</span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
