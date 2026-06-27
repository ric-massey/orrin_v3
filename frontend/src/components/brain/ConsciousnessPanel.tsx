import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Brain, Scale, Zap, ShieldAlert, Workflow, Radio, History, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { API } from "@/lib/cognitive";
import { fetchJSON, TTL } from "@/lib/fetchJSON";
import { useLexicon } from "@/lib/lexicon";
import { boxForSource, navigateTo } from "@/lib/navigate";
import { TelemetryState, WorkspaceCandidate, WorkspaceConscious } from "@/lib/telemetry";
import { usePoll } from "@/lib/usePoll";
import { cn } from "@/lib/utils";
import PanelInfo from "./PanelInfo";
import { PanelSubtitle } from "./Lex";
import { HitMissStrip } from "./viz";

/**
 * The §19 Consciousness panel (dual_process_loop.md): the window into the
 * three-role interplay — brought up to the same drill-down depth as its
 * siblings (UI_FIXES Fix 4). It now shows:
 *   • Conscious now    — the single Global-Workspace winner this cycle…
 *   • The competition  — …WITH the ranked runners-up that almost won (the
 *                        "losers" used to be computed then discarded).
 *   • Stream           — the actual stream of conscious moments the panel is
 *                        named for (tail of conscious_stream.json).
 *   • Breakthroughs    — what the Monitor OFFERED (it competes, never seizes).
 *   • Watchdog         — the dumb structural stall-detector (fires regardless, I12).
 *   • Executive lane   — the backgrounded plan-step "dribble", queue rows included.
 * Clicking any moment opens a detail drawer (full content, salience, verdict).
 */

// Source of the conscious winner → a colour, so you can see *where* awareness came from.
const SOURCE_COLOR: Record<string, string> = {
  user: "#3b82f6",
  affect: "#ec4899",
  signal: "#a855f7",
  goal: "#22c55e",
  monitor: "#f59e0b",
  breakthrough: "#f59e0b",
  action: "#06b6d4",
  thought: "#94a3b8",
  binding: "#14b8a6",
};
const sourceColor = (s?: string) => SOURCE_COLOR[(s || "").toLowerCase()] || "#64748b";

function shortId(id?: string | null): string {
  if (!id) return "—";
  return id.length > 10 ? id.slice(0, 8) + "…" : id;
}

function relTime(ts?: number): string {
  if (!ts) return "";
  const ms = Date.now() - ts * 1000;
  if (isNaN(ms) || ms < 0) return "";
  if (ms < 15_000) return "now";
  if (ms < 60_000) return `${Math.round(ms / 1000)}s`;
  if (ms < 3_600_000) return `${Math.round(ms / 60_000)}m`;
  if (ms < 86_400_000) return `${Math.round(ms / 3_600_000)}h`;
  return `${Math.round(ms / 86_400_000)}d`;
}

interface Moment extends WorkspaceConscious {
  ts?: number;
}

// Detail drawer for one conscious moment (mirrors FnDetailDrawer/GoalDrawer).
function MomentDrawer({
  moment,
  competition,
  onClose,
}: {
  moment: Moment;
  competition?: WorkspaceCandidate[];
  onClose: () => void;
}) {
  const color = sourceColor(moment.source);
  return (
    <div role="dialog" aria-modal="true" aria-label="Broadcast moment" className="absolute inset-y-0 right-0 z-30 flex w-[min(380px,90%)] flex-col border-l border-border bg-card/95 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Back">
          <ArrowLeft className="h-4 w-4" />
        </button>
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold">Broadcast moment</span>
        {boxForSource(moment.source) && boxForSource(moment.source) !== "consciousness" ? (
          <button
            onClick={() => {
              navigateTo(boxForSource(moment.source)!);
              onClose();
            }}
            className="rounded-full px-2 py-0.5 text-[10px] underline-offset-2 hover:underline"
            style={{ background: `${color}22`, color }}
            title="Go to the panel this came from"
          >
            {moment.source}
          </button>
        ) : (
          <span className="rounded-full px-2 py-0.5 text-[10px]" style={{ background: `${color}22`, color }}>
            {moment.source || "—"}
          </span>
        )}
        <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close">
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3 text-[12px]">
        <p className="whitespace-pre-wrap rounded-md bg-muted/40 p-2 text-[12px] leading-relaxed text-foreground/95">
          {moment.content || "—"}
        </p>

        <div className="mt-2 space-y-1.5 text-[11px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <span className="w-20 text-[9px] font-semibold uppercase tracking-wide">Salience</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-secondary">
              <div className="h-full rounded-full" style={{ width: `${Math.round((moment.salience || 0) * 100)}%`, background: color }} />
            </div>
            <span className="tabular-nums">{(moment.salience ?? 0).toFixed(2)}</span>
          </div>
          {moment.kind && (
            <div><span className="mr-2 text-[9px] font-semibold uppercase tracking-wide">Kind</span>{moment.kind}</div>
          )}
          {moment.wants && (
            <div>
              <span className="mr-2 text-[9px] font-semibold uppercase tracking-wide">Wants</span>
              <span title="The route the offerer asked the deliberate lane to take. It biases the next pick — it never preempts (I7). Whether it was honored shows up in §20.1 dismissal-recalibration (the 'quieted' badges).">→ {moment.wants}</span>
            </div>
          )}
          {moment.source === "binding" && moment.facets && (
            <div className="mt-2 rounded-md border border-teal-500/20 bg-teal-500/5 p-2">
              <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-teal-500">
                Bound situation
              </div>
              <div className="flex flex-wrap gap-1">
                {Object.entries(moment.facets).map(([key, value]) => (
                  <span key={key} className="rounded-full bg-secondary px-2 py-0.5 text-[9px] text-foreground/80">
                    {key}: {typeof value === "object" ? JSON.stringify(value) : String(value)}
                  </span>
                ))}
              </div>
            </div>
          )}
          {moment.ts != null && (
            <div><span className="mr-2 text-[9px] font-semibold uppercase tracking-wide">When</span>{new Date(moment.ts * 1000).toLocaleString()} ({relTime(moment.ts)} ago)</div>
          )}
        </div>

        {competition && competition.length > 0 && (
          <div className="mt-3">
            <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">
              The competition this cycle (post-habituation)
            </div>
            <div className="space-y-1">
              {competition.map((c, i) => {
                const isWinner = c.content === moment.content;
                return (
                  <div
                    key={i}
                    className={cn("rounded-md border px-2 py-1", isWinner ? "border-foreground/30 bg-foreground/5" : "border-border bg-card/40 opacity-80")}
                    style={{ borderLeft: `3px solid ${sourceColor(c.source)}` }}
                  >
                    <div className="truncate text-[11px] text-foreground/85" title={c.content}>{c.content}</div>
                    <div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-muted-foreground">
                      <span style={{ color: sourceColor(c.source) }}>{c.source}</span>
                      {isWinner && <span className="font-semibold text-foreground/70">won</span>}
                      <span className="ml-auto tabular-nums">{(c.salience ?? 0).toFixed(2)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ConsciousnessPanel({ telemetry }: { telemetry: TelemetryState }) {
  const [tab, setTab] = useState<"now" | "stream" | "verdicts">("now");
  const [stream, setStream] = useState<Moment[]>([]);
  const [drawer, setDrawer] = useState<{ moment: Moment; withCompetition?: boolean } | null>(null);
  const { t, tip } = useLexicon();

  const conscious = telemetry.workspace?.conscious;
  const candidates = telemetry.workspace?.candidates || [];
  const breakthroughs = useMemo(
    () => (telemetry.monitor?.recent_breakthroughs || []).slice().sort((a, b) => (b.salience || 0) - (a.salience || 0)),
    [telemetry.monitor],
  );
  const watchdog = useMemo(
    () => (telemetry.monitor?.watchdog || []).slice().sort((a, b) => (b.cycles_since_advance || 0) - (a.cycles_since_advance || 0)),
    [telemetry.monitor],
  );
  const exec = telemetry.executive;
  const queue = exec?.queue || [];
  const armedCount = watchdog.filter((w) => w.armed).length;

  // Poll the persisted conscious stream while the Stream tab is open — the
  // actual "stream of consciousness" the panel is named for (Fix 4 step 1).
  useEffect(() => {
    if (tab !== "stream") return;
    let stop = false;
    const load = () =>
      fetchJSON<{ moments?: Moment[] }>(`${API}/consciousness?n=80`, { ttlMs: TTL.short })
        .then((d) => { if (!stop && Array.isArray(d.moments)) setStream(d.moments); })
        .catch(() => {});
    load();
    const id = setInterval(load, 5_000);
    return () => { stop = true; clearInterval(id); };
  }, [tab]);

  const hasAny = conscious || breakthroughs.length || watchdog.length || exec;
  // Runners-up = the ranked competition minus the winner's own row.
  const runnersUp = useMemo(
    () => candidates.filter((c) => c.content !== conscious?.content).slice(0, 5),
    [candidates, conscious],
  );

  return (
    <Card id="box-consciousness" className="relative flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-col items-stretch gap-2 space-y-0 pb-2 sm:flex-row sm:items-center sm:justify-between">
        <CardTitle className="flex min-w-0 flex-wrap items-center gap-2 text-sm font-medium text-muted-foreground">
          <Brain className="h-4 w-4 text-signal-accent" /> <span title={tip("consciousness_title")}>{t("consciousness_title")}</span>
          <PanelInfo
            title="Attention arbitration (Global Workspace)"
            perspective="in-attention"
            what="What holds attention right now. Each cycle every subsystem offers content (a signal, the goal, a candidate thought); they compete on salience and ONE winner is selected and broadcast to everything else. You see the winner, the ranked runners-up that almost won, the Monitor's interrupt requests (it competes, never seizes), and the structural watchdog. The Stream tab is the persisted broadcast log."
            source="workspace/monitor/executive blocks via the telemetry socket · Stream: GET /api/attention over brain/data/conscious_stream.json"
            good="A broadcast log that moves between sources (not stuck on one signal — habituation working), and interrupt requests that get honored when they matter."
            src={{ file: "brain/cognition/global_workspace.py", start: 136, end: 230, label: "update_workspace" }}
          />
          <PanelSubtitle id="consciousness_sub" />
        </CardTitle>
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <div className="flex rounded-md border border-border p-0.5">
            {(["now", "stream", "verdicts"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setTab(k)}
                title={k === "verdicts" ? `${t("verdicts_label")} — §20.1 dismissal-recalibration over time` : undefined}
                className={cn("flex items-center gap-1 rounded px-2 py-0.5 text-[11px] font-medium capitalize transition-colors", tab === k ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground")}
              >
                {k === "stream" && <History className="h-3 w-3" />}
                {k === "verdicts" && <Scale className="h-3 w-3" />}
                {k}
              </button>
            ))}
          </div>
          <span className="hidden text-[11px] text-muted-foreground/60 xl:inline" title={tip("workspace_tagline")}>{t("workspace_tagline")}</span>
        </div>
      </CardHeader>

      <CardContent className="min-h-0 flex-1 p-0">
        {tab === "stream" ? (
          <div className="scrollbar-thin h-full space-y-1 overflow-auto px-3 pb-3">
            <div className="py-1 text-[9px] text-muted-foreground">newest first · click a moment for detail</div>
            {stream.length === 0 && (
              <div className="py-10 text-center text-sm text-muted-foreground">No persisted broadcast moments yet.</div>
            )}
            {[...stream].reverse().map((m, i) => (
              <button
                key={`${m.ts ?? 0}-${i}`}
                onClick={() => setDrawer({ moment: m })}
                className="block w-full rounded-md border border-border bg-card/40 px-2 py-1.5 text-left transition-colors hover:bg-secondary/40"
                style={{ borderLeft: `3px solid ${sourceColor(m.source)}` }}
              >
                <div className="truncate text-[11.5px] text-foreground/90" title={m.content}>{m.content}</div>
                <div className="mt-0.5 flex items-center gap-1.5 text-[9px] text-muted-foreground">
                  <span style={{ color: sourceColor(m.source) }}>{m.source}</span>
                  <span className="tabular-nums">{(m.salience ?? 0).toFixed(2)}</span>
                  <span className="ml-auto tabular-nums">{relTime(m.ts)}</span>
                </div>
              </button>
            ))}
          </div>
        ) : tab === "verdicts" ? (
          <VerdictsView active={tab === "verdicts"} />
        ) : (
          <div className="scrollbar-thin h-full space-y-3 overflow-auto px-3 pb-3">
            {!hasAny && (
              <div className="py-10 text-center text-sm text-muted-foreground">
                Waiting for the workspace… (no conscious content emitted yet)
              </div>
            )}

            {/* ── Conscious now: the single winner (one theatre, Baars) ── */}
            {conscious && (
              <Section icon={<Radio className="h-3 w-3" />} label={t("conscious_now")} labelTip={tip("conscious_now")}>
                <button
                  onClick={() => setDrawer({ moment: conscious, withCompetition: true })}
                  className="block w-full rounded-lg border bg-card/60 px-3 py-2.5 text-left transition-colors hover:bg-secondary/30"
                  style={{ borderLeft: `3px solid ${sourceColor(conscious.source)}` }}
                  title="Click for the full moment + this cycle's competition"
                >
                  <p className="text-[13px] font-medium leading-snug text-foreground/95">
                    {conscious.content || "—"}
                  </p>
                  <div className="mt-2 flex items-center gap-2">
                    <SourceChip source={conscious.source} />
                    {conscious.source === "binding" && (
                      <span className="rounded-full bg-teal-500/10 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-teal-500">
                        bound situation
                      </span>
                    )}
                    {conscious.kind && (
                      <span className="text-[10px] text-muted-foreground">· {conscious.kind}</span>
                    )}
                    {conscious.wants && (
                      <span className="text-[10px] text-muted-foreground/70">→ wants {conscious.wants}</span>
                    )}
                    <div className="ml-auto flex items-center gap-1.5">
                      <div className="h-1 w-16 overflow-hidden rounded-full bg-secondary">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${Math.round((conscious.salience || 0) * 100)}%`, background: sourceColor(conscious.source) }}
                        />
                      </div>
                      <span className="text-[10px] tabular-nums text-muted-foreground">
                        {(conscious.salience ?? 0).toFixed(2)}
                      </span>
                    </div>
                  </div>
                </button>

                {/* The competition: the runners-up, ranked — what ALMOST won (Fix 4 step 2). */}
                {runnersUp.length > 0 && (
                  <div className="mt-1 space-y-0.5">
                    <div className="px-1 text-[9px] text-muted-foreground/70">also competed (didn't win):</div>
                    {runnersUp.map((c, i) => (
                      <div key={i} className="flex items-center gap-1.5 rounded px-1.5 py-0.5 opacity-75">
                        <span className="h-1.5 w-1.5 flex-none rounded-full" style={{ background: sourceColor(c.source) }} />
                        <span className="min-w-0 flex-1 truncate text-[10.5px] text-muted-foreground" title={c.content}>{c.content}</span>
                        <span className="text-[9px] tabular-nums text-muted-foreground/70">{(c.salience ?? 0).toFixed(2)}</span>
                      </div>
                    ))}
                  </div>
                )}
              </Section>
            )}

            {/* ── Executive lane: the backgrounded dribble ── */}
            {exec && (
              <Section icon={<Workflow className="h-3 w-3" />} label={t("executive_lane")} labelTip={tip("executive_lane")}>
                <div className="rounded-lg border border-border bg-card/40 px-3 py-2">
                  {exec.active_fn ? (
                    <>
                      <div className="flex items-center gap-1.5">
                        <span className="inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-signal-ok animate-pulse" />
                        {/* Fix 4 step 4: provenance links — the fn lights its node
                            on the Sphere, the goal opens in the Goals panel. */}
                        <button
                          onClick={() => navigateTo("sphere", String(exec.active_fn))}
                          className="font-mono text-[11px] text-foreground/85 underline-offset-2 hover:underline"
                          title="Show this function on the Function-call graph"
                        >
                          {exec.active_fn}
                        </button>
                        {exec.goal_title && (
                          <button
                            onClick={() => navigateTo("goals-panel", String(exec.goal_id || exec.goal_title))}
                            className="truncate text-[11px] text-muted-foreground underline-offset-2 hover:underline"
                            title="Open this goal in the Goals panel"
                          >
                            · {exec.goal_title}
                          </button>
                        )}
                      </div>
                      {exec.active_step && (
                        <p className="mt-1 truncate text-[11px] text-muted-foreground/80" title={exec.active_step}>
                          {exec.active_step}
                        </p>
                      )}
                    </>
                  ) : (
                    <span className="text-[11px] text-muted-foreground">{t("exec_idle")}</span>
                  )}
                  {/* Fix 10.3: the queue is a LIST, not a count — show the rows,
                      each linking to its goal in the Goals panel. */}
                  {queue.length > 0 && (
                    <div className="mt-1.5 space-y-0.5 border-t border-border/60 pt-1.5">
                      <div className="text-[9px] font-semibold uppercase tracking-wide text-muted-foreground/70">
                        Committed queue · {queue.length}
                      </div>
                      {queue.slice(0, 5).map((g, i) => (
                        <button
                          key={i}
                          onClick={() => navigateTo("goals-panel", String(g.goal_id || g.title || ""))}
                          className="flex w-full items-baseline gap-1.5 rounded px-0.5 text-left hover:bg-secondary/40"
                          title="Open this goal in the Goals panel"
                        >
                          <span className="min-w-0 flex-1 truncate text-[10.5px] text-foreground/80">{g.title || "(untitled)"}</span>
                          {g.next_step && (
                            <span className="min-w-0 max-w-[45%] truncate text-[9.5px] text-muted-foreground/70">→ {g.next_step}</span>
                          )}
                        </button>
                      ))}
                      {queue.length > 5 && (
                        <div className="text-[9px] text-muted-foreground/60">+{queue.length - 5} more</div>
                      )}
                    </div>
                  )}
                </div>
              </Section>
            )}

            {/* ── Breakthroughs the Monitor offered (it competes, never seizes) ── */}
            {breakthroughs.length > 0 && (
              <Section icon={<Zap className="h-3 w-3" />} label={`${t("breakthroughs")} · ${breakthroughs.length}`} labelTip={tip("breakthroughs")}>
                <div className="space-y-1">
                  {breakthroughs.map((b, i) => (
                    <div key={i} className="flex items-center gap-2 rounded-md border border-border bg-card/40 px-2 py-1">
                      <span className="text-[11px] font-medium text-foreground/85">{b.kind}</span>
                      {b.wants && <span className="text-[10px] text-muted-foreground/70">→ {b.wants}</span>}
                      {b.threshold != null && b.threshold < 0.999 && (
                        <span
                          className="rounded bg-secondary px-1 py-0 text-[9px] tabular-nums text-muted-foreground/80"
                          title={`Dismissal-recalibration (§20.1): this kind is being quieted — learned threshold ${b.threshold.toFixed(2)}× (it kept being dismissed).`}
                        >
                          quieted ×{b.threshold.toFixed(2)}
                        </span>
                      )}
                      <div className="ml-auto flex items-center gap-1.5">
                        <div className="h-1 w-12 overflow-hidden rounded-full bg-secondary">
                          <div className="h-full rounded-full bg-signal-warn" style={{ width: `${Math.round((b.salience || 0) * 100)}%` }} />
                        </div>
                        <span className="text-[10px] tabular-nums text-muted-foreground">{(b.salience ?? 0).toFixed(2)}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </Section>
            )}

            {/* ── Watchdog board: the dumb structural stall-detector (I12) ── */}
            {watchdog.length > 0 && (
              <Section
                icon={<ShieldAlert className="h-3 w-3" />}
                label={`${t("watchdog")} · ${armedCount > 0 ? `${armedCount} armed` : "all clear"}`}
                labelTip={tip("watchdog")}
              >
                <div className="space-y-1">
                  {watchdog.map((w, i) => (
                    <div
                      key={i}
                      className={cn(
                        "flex items-center gap-2 rounded-md border px-2 py-1",
                        w.armed ? "border-signal-warn/50 bg-signal-warn/10" : "border-border bg-card/40",
                      )}
                    >
                      <span className="font-mono text-[10px] text-muted-foreground" title={w.goal_id}>{shortId(w.goal_id)}</span>
                      <span className={cn("ml-auto text-[11px] tabular-nums", w.armed ? "font-semibold text-signal-warn" : "text-muted-foreground")}>
                        {w.cycles_since_advance} cyc idle
                      </span>
                      {w.armed && <span className="text-[9px] font-semibold uppercase tracking-wide text-signal-warn">firing</span>}
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}

        {drawer && (
          <MomentDrawer
            moment={drawer.moment}
            competition={drawer.withCompetition ? candidates : undefined}
            onClose={() => setDrawer(null)}
          />
        )}
      </CardContent>
    </Card>
  );
}

function Section({ icon, label, labelTip, children }: { icon: React.ReactNode; label: string; labelTip?: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground" title={labelTip}>
        {icon} {label}
      </div>
      {children}
    </div>
  );
}

/** The winner's source as a chip — clickable when the source has an owning box
 *  (Fix 4 step 4: goal → Goals, affect/signal → Affect rings, memory → Memory).
 *  Rendered as a span (it sits inside the winner card, which is a <button> —
 *  nesting real buttons would be invalid DOM). */
function SourceChip({ source, onNavigate }: { source?: string; onNavigate?: () => void }) {
  const color = sourceColor(source);
  const box = boxForSource(source);
  const style = { background: `${color}22`, color };
  const cls = "rounded px-1.5 py-0 text-[9px] font-semibold uppercase tracking-wide";
  if (!box || box === "consciousness") {
    return <span className={cls} style={style}>{source || "—"}</span>;
  }
  return (
    <span
      role="button"
      tabIndex={0}
      onClick={(e) => {
        e.stopPropagation();
        navigateTo(box);
        onNavigate?.();
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          e.stopPropagation();
          navigateTo(box);
          onNavigate?.();
        }
      }}
      className={cn(cls, "cursor-pointer underline-offset-2 hover:underline")}
      style={style}
      title="Go to the panel this came from"
    >
      {source}
    </span>
  );
}

/** Fix 4 step 5 — §20.1 dismissal-recalibration, browsable over time: per kind,
 *  how often its breakthroughs were honored vs dismissed, the recent verdict
 *  strip, and the current learned bias (how quieted the kind is now). */
function VerdictsView({ active }: { active: boolean }) {
  const data = usePoll<{ verdicts?: { ts?: string; kind?: string; honored?: boolean; bias?: number }[]; bias?: Record<string, number> }>(
    active ? `${API}/verdicts?n=200` : "",
    15_000,
  );
  const verdicts = data?.verdicts || [];
  const bias = data?.bias || {};
  const kinds = useMemo(() => {
    const byKind = new Map<string, { honored: number; dismissed: number; recent: (boolean | null)[] }>();
    for (const v of verdicts) {
      const k = v.kind || "?";
      const rec = byKind.get(k) || { honored: 0, dismissed: 0, recent: [] };
      if (v.honored) rec.honored += 1;
      else rec.dismissed += 1;
      rec.recent.push(!!v.honored);
      byKind.set(k, rec);
    }
    for (const k of Object.keys(bias)) if (!byKind.has(k)) byKind.set(k, { honored: 0, dismissed: 0, recent: [] });
    return [...byKind.entries()].sort((a, b) => b[1].honored + b[1].dismissed - (a[1].honored + a[1].dismissed));
  }, [verdicts, bias]);

  return (
    <div className="scrollbar-thin h-full space-y-3 overflow-auto px-3 pb-3 pt-1">
      <p className="text-[10px] leading-snug text-muted-foreground">
        Who watches the watcher (§20.1): when the deliberate mind <b>dismisses</b> a breakthrough kind, the Monitor learns it was
        crying wolf and quiets it; <b>honoring</b> it restores the kind's voice. Structural alarms are never quieted.
      </p>
      {kinds.length === 0 ? (
        <div className="py-8 text-center text-xs text-muted-foreground">No verdicts recorded yet — they accrue as interrupt requests win the broadcast and the deliberate lane reacts.</div>
      ) : (
        <div className="space-y-1.5">
          {kinds.map(([kind, k]) => {
            const b = bias[kind];
            return (
              <div key={kind} className="rounded-md border border-border bg-card/40 px-2 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-[11px] font-medium text-foreground/90">{kind}</span>
                  <span className="text-[9px] text-signal-ok">honored {k.honored}</span>
                  <span className="text-[9px] text-signal-error">dismissed {k.dismissed}</span>
                  {b != null && b < 0.999 && (
                    <span
                      className="ml-auto rounded bg-secondary px-1 py-0 text-[9px] tabular-nums text-muted-foreground/80"
                      title={`Current learned threshold bias ${b.toFixed(2)}× — below 1.0 means this kind is being quieted.`}
                    >
                      quieted ×{b.toFixed(2)}
                    </span>
                  )}
                  {b != null && b >= 0.999 && <span className="ml-auto text-[9px] text-muted-foreground/60">full voice</span>}
                </div>
                {k.recent.length > 0 && (
                  <div className="mt-1">
                    <HitMissStrip results={k.recent.slice(-40)} title="Recent verdicts, oldest → newest (green = honored)" />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {verdicts.length > 0 && (
        <div>
          <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">Recent verdicts</div>
          <div className="space-y-0.5">
            {[...verdicts].reverse().slice(0, 30).map((v, i) => (
              <div key={i} className="flex items-center gap-2 rounded px-1 py-0.5 text-[10px]">
                <span className={v.honored ? "text-signal-ok" : "text-signal-error"}>{v.honored ? "honored" : "dismissed"}</span>
                <span className="text-foreground/80">{v.kind}</span>
                <span className="ml-auto tabular-nums text-muted-foreground/60">
                  {v.ts ? new Date(v.ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : ""}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
