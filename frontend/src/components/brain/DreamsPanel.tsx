import { MoonStar } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { usePoll } from "@/lib/usePoll";
import PanelInfo from "./PanelInfo";
import StaleBadge from "./StaleBadge";
import { LexText, PanelSubtitle } from "./Lex";

/** Dreams box — what it consolidates while idle. Honesty rule from ui_fixes.md:
 *  fresh-run entries are often EMPTY strings for consolidation/recombination,
 *  so an empty sweep renders "slept — nothing consolidated", never blank cards. */

interface Dream { timestamp?: string; consolidation?: string; recombination?: string; processing?: string }
interface Insight { type?: string; text?: string; score?: number; importance?: number }
interface SymbolicDream { timestamp?: string; insights?: Insight[] }

function fmtDate(ts?: string): string {
  if (!ts) return "";
  const d = new Date(ts);
  return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function DreamsPanel() {
  const data = usePoll<{ dreams?: Dream[]; symbolic?: SymbolicDream[]; total?: number }>(`${API}/dreams?n=12`, 30_000);
  const dreams = data?.dreams || [];
  const symbolic = data?.symbolic || [];

  return (
    <Card id="box-dreams" className="flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
          <MoonStar className="h-4 w-4" /> <LexText id="dreams_title" />
          <PanelInfo
            title="Idle consolidation"
            perspective="agent-accessible"
            what="What it does while idle: each idle sweep's consolidation (memories compressed into themes), recombination (distant ideas spliced into something new), and processing notes — plus the symbolic recombination engine's analogy-transfer insights. A sweep with nothing to consolidate says so honestly."
            source="GET /api/dreams over brain/data/dream_log.json · symbolic_dream_log.json"
            good="Sweeps that actually produce consolidations/insights as experience accumulates — early in a run 'slept, nothing consolidated' is the TRUE state, not a bug."
            src={{ file: "brain/cognition/dreaming/dream_cycle.py", start: 1, end: 60, label: "dream_cycle" }}
          />
          <PanelSubtitle id="dreams_sub" />
          <StaleBadge url={`${API}/dreams`} pollMs={30_000} />
        </CardTitle>
        <span className="text-[11px] text-muted-foreground/60">{data?.total ?? 0} sweeps</span>
      </CardHeader>
      <CardContent className="scrollbar-thin min-h-0 flex-1 space-y-3 overflow-auto pb-3">
        {dreams.length === 0 && symbolic.length === 0 ? (
          <div className="py-8 text-center text-xs text-muted-foreground">No idle-consolidation sweeps yet — runs when idle.</div>
        ) : (
          <>
            <div className="space-y-1">
              {[...dreams].reverse().map((d, i) => {
                const empty = !d.consolidation && !d.recombination && !d.processing;
                return (
                  <div key={i} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                    <div className="flex items-baseline gap-2 text-[9px] text-muted-foreground">
                      <span className="font-semibold uppercase tracking-wide">idle sweep</span>
                      <span className="ml-auto tabular-nums">{fmtDate(d.timestamp)}</span>
                    </div>
                    {empty ? (
                      <p className="mt-0.5 text-[10.5px] italic text-muted-foreground">Slept — nothing consolidated this sweep.</p>
                    ) : (
                      <div className="mt-0.5 space-y-0.5 text-[10.5px] leading-snug text-foreground/85">
                        {d.consolidation && <p><span className="text-muted-foreground">consolidated:</span> {d.consolidation}</p>}
                        {d.recombination && <p><span className="text-muted-foreground">recombined:</span> {d.recombination}</p>}
                        {d.processing && <p><span className="text-muted-foreground">processed:</span> {d.processing}</p>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {symbolic.some((s) => (s.insights || []).length > 0) && (
              <div>
                <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Symbolic recombination insights</div>
                <div className="space-y-1">
                  {[...symbolic].reverse().flatMap((s, si) =>
                    (s.insights || []).map((ins, i) => (
                      <div key={`${si}-${i}`} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                        <div className="flex items-baseline gap-2 text-[9px] text-muted-foreground">
                          <span className="rounded bg-secondary px-1.5 py-0 font-mono text-foreground/70">{ins.type || "insight"}</span>
                          {ins.score != null && <span className="ml-auto tabular-nums">score {Number(ins.score).toFixed(2)}</span>}
                        </div>
                        <p className="mt-0.5 text-[10px] leading-snug text-foreground/85" title={ins.text}>{ins.text}</p>
                      </div>
                    )),
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
