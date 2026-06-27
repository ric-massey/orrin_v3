import { Brain, Lock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import { useLexicon } from "@/lib/lexicon";
import { usePolledJSON } from "@/lib/usePolled";
import { useTelemetryState } from "../App";
import InfoDot from "@/components/brain/InfoDot";
import { ROOM_INFO } from "@/lib/roomMetrics";

// Cognition (§9.3): a calm reading of feeds Orrin already produces, arranged as a
// narrative — "what is he doing right now?". Pure composition: the live blocks come
// from the shared telemetry stream; drives/symbolic/peers are polled REST. Honesty
// rule: an empty/stale feed says so, it never renders blank. His private thoughts are
// never fetched or shown (the API already strips them) — that's a trust feature.

interface DrivesFeed {
  drives?: Record<string, number>;
  interoception?: { fn?: string; ema?: number }[];
}
interface SymbolicFeed {
  rules?: { name?: string; rule?: string; hits?: number }[];
  rules_total?: number;
  llm_off?: boolean;
}
interface PeopleFeed {
  peers?: { name?: string }[];
}

export default function Cognition() {
  const t = useLexicon().t;
  const tel = useTelemetryState();
  const drives = usePolledJSON<DrivesFeed>("/api/drives");
  const symbolic = usePolledJSON<SymbolicFeed>("/api/symbolic?n=8");
  const people = usePolledJSON<PeopleFeed>("/api/people");

  const live = tel.source === "live" && tel.connected;

  // Hero pieces (honest fallbacks when a feed hasn't populated).
  const focus = tel.activeFn || tel.activeNode || null;
  const activeGoal = tel.goals.find((g) => g.active) || tel.goals[0] || null;
  const topDrive = topEntry(drives?.drives);

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-6 sm:px-6">
      {/* Hero — one breathing line synced to his ~20s cycle. */}
      <div className={cn("rounded-xl border bg-card p-5 sm:p-6", live && "animate-breathe")}>
        <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
          <Brain className="h-4 w-4" />
          <span>Right now</span>
          <span className="text-border">·</span>
          <StreamDot live={live} stopped={tel.source === "stopped"} />
          <span className="tabular-nums">cycle {tel.cycle}</span>
        </div>
        <p className="text-lg leading-snug sm:text-xl">
          {focus ? (
            <>
              Orrin is <Hl>{focus}</Hl>
              {topDrive && (
                <>
                  {" "}because <Hl>{topDrive}</Hl>
                </>
              )}
              {activeGoal && (
                <>
                  {" "}while pursuing <Hl>{activeGoal.title}</Hl>
                </>
              )}
              .
            </>
          ) : (
            <span className="text-muted-foreground">
              {tel.source === "stopped"
                ? "Orrin is stopped — his mind is frozen where it was."
                : "Waiting for his first thought this session…"}
            </span>
          )}
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <Block title={t("cog_winner")} info="workspace">
          {tel.workspace?.conscious?.content ? (
            <div className="space-y-1">
              <p className="text-sm">{tel.workspace.conscious.content}</p>
              <Meta>
                from {tel.workspace.conscious.source || "—"}
                {tel.workspace.conscious.salience != null &&
                  ` · salience ${tel.workspace.conscious.salience.toFixed(2)}`}
              </Meta>
            </div>
          ) : (
            <Empty>Nothing has taken the global workspace yet.</Empty>
          )}
        </Block>

        <Block title={t("cog_goal")} info="cog_goal">
          {activeGoal ? (
            <div className="space-y-1">
              <p className="text-sm">{activeGoal.title}</p>
              <Meta>
                {activeGoal.current_step
                  ? `step: ${activeGoal.current_step}`
                  : activeGoal.status}
                {activeGoal.steps_total
                  ? ` · ${activeGoal.steps_done ?? 0}/${activeGoal.steps_total}`
                  : ""}
              </Meta>
            </div>
          ) : (
            <Empty>He isn't pursuing a goal right now.</Empty>
          )}
        </Block>

        <Block title={t("cog_competing")} info="workspace" className="sm:col-span-2">
          {tel.workspace?.candidates && tel.workspace.candidates.length > 0 ? (
            <ul className="space-y-1.5">
              {[...tel.workspace.candidates]
                .sort((a, b) => (b.salience ?? 0) - (a.salience ?? 0))
                .slice(0, 6)
                .map((c, i) => (
                  <li key={i} className="flex items-center gap-2 text-sm">
                    <span className="w-10 shrink-0 text-right tabular-nums text-xs text-muted-foreground">
                      {c.salience != null ? c.salience.toFixed(2) : "—"}
                    </span>
                    <span className="truncate">{c.content || c.source || "(unlabelled)"}</span>
                    {i === 0 && (
                      <span className="ml-auto shrink-0 rounded-full bg-signal-ok/15 px-1.5 py-0.5 text-[10px] font-medium text-signal-ok">
                        winning
                      </span>
                    )}
                  </li>
                ))}
            </ul>
          ) : (
            <Empty>Nothing is competing for attention.</Empty>
          )}
        </Block>

        <Block title={t("cog_drives")} info="drives">
          {drives?.drives && Object.keys(drives.drives).length > 0 ? (
            <ul className="space-y-1">
              {Object.entries(drives.drives)
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .slice(0, 5)
                .map(([k, v]) => (
                  <li key={k} className="flex items-center gap-2 text-sm">
                    <span className="w-28 shrink-0 truncate capitalize">{k}</span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                      <span
                        className="block h-full bg-primary/70"
                        style={{ width: `${Math.max(0, Math.min(1, Number(v))) * 100}%` }}
                      />
                    </span>
                  </li>
                ))}
            </ul>
          ) : (
            <Empty>No drive pressure reported.</Empty>
          )}
        </Block>

        <Block title={t("cog_symbolic")} info="symbolic">
          {symbolic?.rules && symbolic.rules.length > 0 ? (
            <div className="space-y-1">
              <Meta>
                {symbolic.rules_total ?? symbolic.rules.length} learned rules
                {symbolic.llm_off ? " · running without the LLM" : ""}
              </Meta>
              <ul className="space-y-1">
                {symbolic.rules.slice(0, 4).map((r, i) => (
                  <li key={i} className="truncate text-sm">
                    {r.name || r.rule || "(rule)"}
                    {r.hits != null && <span className="text-muted-foreground"> · {r.hits} hits</span>}
                  </li>
                ))}
              </ul>
            </div>
          ) : (
            <Empty>No symbolic rules have fired yet.</Empty>
          )}
        </Block>

        <Block title="Thinking cost" className="sm:col-span-2">
          {tel.llmCost ? (
            (() => {
              const lc = tel.llmCost;
              const ratio = Math.max(0, Math.min(1, lc.symbolic_ratio ?? 0));
              return (
                <div className="space-y-2">
                  <Meta>
                    {(ratio * 100).toFixed(0)}% of reasoning ran symbolically (offline)
                    {" · "}
                    {lc.llm_calls ?? 0} LLM · {lc.symbolic_hits ?? 0} symbolic
                  </Meta>
                  <span className="block h-1.5 overflow-hidden rounded-full bg-muted">
                    <span
                      className="block h-full bg-signal-ok/70"
                      style={{ width: `${ratio * 100}%` }}
                    />
                  </span>
                  <Meta>
                    reasoning cache: {lc.cache_live ?? 0} live / {lc.cache_entries ?? 0} entries
                  </Meta>
                </div>
              );
            })()
          ) : (
            <Empty>No LLM activity recorded this session yet.</Empty>
          )}
        </Block>

        <Block title={t("cog_peers")} info="peers" className="sm:col-span-2">
          {people?.peers && people.peers.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {people.peers.map((p, i) => (
                <span key={i} className="rounded-full border bg-background px-2 py-0.5 text-xs">
                  {p.name || "peer"}
                </span>
              ))}
            </div>
          ) : (
            <Empty>No inner voices are pressing right now.</Empty>
          )}
        </Block>
      </div>

      {/* The one deliberate boundary — labelled, not hidden (§8.5). */}
      <div className="flex items-center gap-2 rounded-lg border bg-card px-4 py-2.5 text-xs text-muted-foreground">
        <Lock className="h-3.5 w-3.5 shrink-0" />
        {useLexicon().t("cog_private")}
      </div>
    </div>
  );
}

function Block({
  title,
  info,
  children,
  className,
}: {
  title: string;
  info?: keyof typeof ROOM_INFO;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-1 text-sm font-medium text-muted-foreground">
          {title}
          {info && <InfoDot info={ROOM_INFO[info]} />}
        </CardTitle>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

const Hl = ({ children }: { children: React.ReactNode }) => (
  <span className="font-semibold text-foreground">{children}</span>
);
const Meta = ({ children }: { children: React.ReactNode }) => (
  <p className="text-xs text-muted-foreground">{children}</p>
);
const Empty = ({ children }: { children: React.ReactNode }) => (
  <p className="text-sm italic text-muted-foreground">{children}</p>
);

function StreamDot({ live, stopped }: { live: boolean; stopped: boolean }) {
  return (
    <span
      className={cn(
        "inline-block h-2 w-2 rounded-full",
        live ? "bg-signal-ok" : stopped ? "bg-muted-foreground" : "bg-signal-warn",
      )}
    />
  );
}

function topEntry(obj?: Record<string, number>): string | null {
  if (!obj) return null;
  const entries = Object.entries(obj);
  if (entries.length === 0) return null;
  return entries.sort((a, b) => Number(b[1]) - Number(a[1]))[0][0];
}
