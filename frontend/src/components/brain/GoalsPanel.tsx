import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ArrowLeft, Check, ChevronDown, Circle, Target, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { API } from "@/lib/cognitive";
import { fetchJSON, TTL } from "@/lib/fetchJSON";
import { useNavTarget } from "@/lib/navigate";
import PanelInfo from "./PanelInfo";
import { PanelSubtitle } from "./Lex";
import StaleBadge from "./StaleBadge";
import { TelemetryState } from "@/lib/telemetry";
import { cn } from "@/lib/utils";

/** Format a timestamp as "Mon D, HH:MM" (date + time). Distinct from
 *  lib/utils.ts `fmtTime`, which renders epoch-seconds as HH:MM:SS only. */
function fmtDateTime(ts?: string | number): string {
  if (ts == null) return "";
  const d = typeof ts === "number" ? new Date(ts < 1e12 ? ts * 1000 : ts) : new Date(ts);
  return isNaN(d.getTime()) ? "" : d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

interface Milestone { text: string; met?: boolean; met_at?: string }
interface PlanStep { step: string; status?: string }
interface HistoryEvent { event: string; timestamp?: string }
interface GoalDetail {
  id?: string;
  title: string;
  status: string;
  tier?: string;
  priority?: string | number | null;
  kind?: string;
  tags?: string[];
  serves?: string;
  description?: string;
  driven_by?: string;
  milestones?: Milestone[];
  plan?: PlanStep[];
  history?: HistoryEvent[];
  completed_timestamp?: string;
  created_at?: string;
  last_updated?: string;
  raw?: Record<string, unknown>;
}
interface Artifact { id?: string; ts?: string; event_type?: string; content: string; importance?: string | number; on_topic?: boolean; in_window?: boolean }

type Bucket = "active" | "open" | "completed" | "failed";
function bucketOf(status: string): Bucket {
  const s = (status || "").toLowerCase();
  if (/fail|abandon|block/.test(s)) return "failed";
  if (/complete|done|closed/.test(s)) return "completed";
  if (/active|progress/.test(s)) return "active";
  return "open";
}
const BUCKET_COLOR: Record<Bucket, string> = { active: "#3b82f6", open: "#eab308", completed: "#22c55e", failed: "#ef4444" };
const key = (g: { id?: string | null; title: string }) => String(g.id || g.title);

export default function GoalsPanel({ telemetry }: { telemetry: TelemetryState }) {
  const [all, setAll] = useState<GoalDetail[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [openSection, setOpenSection] = useState<Record<Bucket, boolean>>({ active: true, open: true, completed: false, failed: true });

  // Single stable source: poll /goals (full detail, whole tree). Keep the last
  // non-empty result so a momentary fetch hiccup can't make goals flicker away.
  useEffect(() => {
    let stop = false;
    const load = () =>
      fetchJSON<{ goals?: GoalDetail[] }>(`${API}/goals`)
        .then((d) => { if (!stop && Array.isArray(d.goals) && d.goals.length) setAll(d.goals); })
        .catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // Cross-box provenance links (Fix 4 step 4 / Fix 10.3): the Consciousness
  // panel's executive rows navigate here with a goal id or title — open it.
  useNavTarget("goals-panel", (id) => {
    const hit = all.find((g) => String(g.id) === id || key(g) === id || g.title === id);
    if (hit) setSelected(key(hit));
  });

  // Live "which goal is he on right now" comes from telemetry (the committed goal).
  const activeId = useMemo(() => {
    const a = (telemetry.goals || []).find((g) => g.active);
    return a ? String(a.id || a.title) : null;
  }, [telemetry.goals]);

  const groups = useMemo(() => {
    const g: Record<Bucket, GoalDetail[]> = { active: [], open: [], completed: [], failed: [] };
    for (const goal of all) {
      let b = bucketOf(goal.status);
      if (key(goal) === activeId) b = "active";
      g[b].push(goal);
    }
    // newest-ish first within completed/failed
    g.completed.reverse();
    g.failed.reverse();
    return g;
  }, [all, activeId]);

  const detailsMap = useMemo(() => Object.fromEntries(all.map((g) => [key(g), g])), [all]);
  const sel = selected ? detailsMap[selected] : undefined;

  const counts: Record<Bucket, number> = { active: groups.active.length, open: groups.open.length, completed: groups.completed.length, failed: groups.failed.length };
  const sectionMeta: { b: Bucket; label: string }[] = [
    { b: "active", label: "Active" },
    { b: "open", label: "Open" },
    { b: "failed", label: "Needs another approach" },
    { b: "completed", label: "Completed" },
  ];

  return (
    <Card id="box-goals-panel" className="relative flex h-full flex-col overflow-hidden">
      <CardHeader className="flex-col items-stretch gap-2 space-y-0 pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="flex min-w-0 items-center gap-2 text-sm font-medium text-muted-foreground">
            <Target className="h-4 w-4 text-signal-accent" /> Goals
            <PanelSubtitle id="goals_sub" />
            <PanelInfo
              title="Goals"
              what="What he's trying to do: every goal with its status, plan steps, milestones, and history. Click a goal for the full drawer — including the artifacts he ACTUALLY produced for it, not just the templated plan. The blue 'active' one is the committed goal his deliberate lane is pursuing; the executive lane quietly rotates through the rest of the committed queue."
              source="GET /api/goals over brain/data/goals_mem.json (live committed goal via the socket)"
              good="Goals that close — completed or retired — instead of accumulating; see the Goal health box for the closure funnel."
              src={{ file: "brain/ORRIN_loop.py", start: 252, end: 311, label: "_emit_goals" }}
            />
          </CardTitle>
          <span className="flex items-center gap-2 text-[11px] text-muted-foreground/60">
            {all.length} total
            <StaleBadge url={`${API}/goals`} />
          </span>
        </div>
        {/* summary chips (metrics-strip style) */}
        <div className="flex gap-1.5">
          {(["active", "open", "failed", "completed"] as Bucket[]).map((b) => (
            <div key={b} className="flex flex-1 items-center gap-1.5 rounded-md border border-border bg-card/60 px-2 py-1">
              <span className="h-2 w-2 rounded-full" style={{ background: BUCKET_COLOR[b] }} />
              <span className="text-[15px] font-semibold tabular-nums leading-none">{counts[b]}</span>
              <span className="text-[9px] uppercase tracking-wide text-muted-foreground">{b === "failed" ? "retry" : b}</span>
            </div>
          ))}
        </div>
      </CardHeader>

      <CardContent className="min-h-0 flex-1 p-0">
        <div className="scrollbar-thin h-full overflow-auto px-3 pb-3">
          {all.length === 0 ? (
            <div className="py-10 text-center text-sm text-muted-foreground">Loading goals…</div>
          ) : (
            sectionMeta.map(({ b, label }) =>
              groups[b].length === 0 ? null : (
                <div key={b} className="mb-2">
                  <button
                    onClick={() => setOpenSection((s) => ({ ...s, [b]: !s[b] }))}
                    className="flex w-full items-center gap-1.5 py-1 text-left"
                  >
                    <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform", !openSection[b] && "-rotate-90")} />
                    <span className="h-1.5 w-1.5 rounded-full" style={{ background: BUCKET_COLOR[b] }} />
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</span>
                    <span className="text-[10px] text-muted-foreground/60">{groups[b].length}</span>
                  </button>
                  {openSection[b] && (
                    <div className="flex flex-col gap-1.5">
                      {groups[b].map((g) => (
                        <GoalCard key={key(g)} g={g} active={key(g) === activeId} onClick={() => setSelected(key(g))} />
                      ))}
                    </div>
                  )}
                </div>
              )
            )
          )}
        </div>

        {selected && sel && <GoalDrawer detail={sel} onClose={() => setSelected(null)} />}
      </CardContent>
    </Card>
  );
}

function GoalCard({ g, active, onClick }: { g: GoalDetail; active: boolean; onClick: () => void }) {
  const b = active ? "active" : bucketOf(g.status);
  const color = BUCKET_COLOR[b];
  const ms = g.milestones || [];
  const metN = ms.filter((m) => m.met).length;
  const plan = g.plan || [];
  const doneN = plan.filter((p) => /complet/i.test(p.status || "")).length;
  const unmetComplete = /complete|done/i.test(g.status) && ms.length > 0 && metN < ms.length;
  const pct = ms.length > 0 ? (metN / ms.length) * 100 : plan.length > 0 ? (doneN / plan.length) * 100 : 0;

  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full rounded-lg border bg-card/60 px-3 py-2 text-left transition-colors hover:bg-secondary/40",
        active ? "border-signal-accent/60 bg-signal-accent/[0.06]" : "border-border"
      )}
      style={{ borderLeft: `3px solid ${color}` }}
    >
      <div className="flex items-start gap-2">
        {active && <span className="mt-1 inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-signal-accent animate-pulse" />}
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium" title={g.title}>{g.title}</span>
        {unmetComplete && <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-signal-warn" />}
      </div>

      <div className="mt-1.5 flex items-center gap-2">
        <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary">
          <div className="h-full rounded-full" style={{ width: `${pct}%`, background: color }} />
        </div>
        {ms.length > 0 && <span className="text-[10px] tabular-nums text-muted-foreground">{metN}/{ms.length} done</span>}
      </div>

      <div className="mt-1 flex flex-wrap items-center gap-1.5">
        {g.tier && <span className="text-[9px] uppercase tracking-wider text-muted-foreground">{g.tier}</span>}
        {g.serves && <span className="truncate text-[10px] text-muted-foreground/70" title={g.serves}>↳ {g.serves}</span>}
      </div>
    </button>
  );
}

// Right-side drawer: honest Overview, What he actually produced (correlated
// long-memory artifacts + provenance), and the Raw record.
function GoalDrawer({ detail, onClose }: { detail: GoalDetail; onClose: () => void }) {
  const [tab, setTab] = useState<"overview" | "produced" | "raw">("overview");
  const [arts, setArts] = useState<{ list: Artifact[]; kws: string[]; loading: boolean }>({ list: [], kws: [], loading: false });

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (tab !== "produced" || !detail.id) return;
    setArts((a) => ({ ...a, loading: true }));
    fetchJSON<{ artifacts?: Artifact[]; topic_keywords?: string[] }>(`${API}/goal_artifacts?id=${encodeURIComponent(detail.id)}`, { ttlMs: TTL.short })
      .then((d) => setArts({ list: Array.isArray(d.artifacts) ? d.artifacts : [], kws: d.topic_keywords || [], loading: false }))
      .catch(() => setArts({ list: [], kws: [], loading: false }));
  }, [tab, detail.id]);

  const status = detail.status || "";
  const milestones = detail.milestones || [];
  const plan = detail.plan || [];
  const history = detail.history || [];
  const metN = milestones.filter((m) => m.met).length;
  const doneSteps = plan.filter((p) => /complet/i.test(p.status || "")).length;
  const unmetButComplete = /complete|done/i.test(status) && milestones.length > 0 && metN < milestones.length;

  return (
    <div role="dialog" aria-modal="true" aria-label="Goal details" className="absolute inset-y-0 right-0 z-30 flex w-[min(440px,96%)] flex-col border-l border-border bg-card/95 shadow-2xl backdrop-blur">
      <div className="flex items-center gap-2 border-b border-border px-3 py-2.5">
        <button onClick={onClose} aria-label="Back" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><ArrowLeft className="h-4 w-4" /></button>
        <span className="min-w-0 flex-1 truncate text-[13px] font-semibold" title={detail.title}>{detail.title}</span>
        <Badge variant={/complete|done/i.test(status) ? "ok" : /fail/i.test(status) ? "warn" : "info"} className="px-1.5 py-0 text-[10px]">{status}</Badge>
        <button onClick={onClose} aria-label="Close" className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><X className="h-4 w-4" /></button>
      </div>

      <div className="flex border-b border-border text-[11px]">
        {([["overview", "Overview"], ["produced", "What he produced"], ["raw", "Raw"]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={cn("flex-1 px-2 py-1.5 font-medium transition-colors", tab === k ? "border-b-2 border-foreground text-foreground" : "text-muted-foreground hover:text-foreground")}>{l}</button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-3 text-[12px]">
        {tab === "overview" && (
          <div className="space-y-3">
            {unmetButComplete && (
              <div className="flex items-start gap-1.5 rounded-md border border-signal-warn/40 bg-signal-warn/10 px-2 py-1.5 text-[11px] text-signal-warn">
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                <span>Marked <b>complete</b>, but {milestones.length - metN} of {milestones.length} success milestone(s) were never met.</span>
              </div>
            )}
            <div className="flex flex-wrap gap-1.5 text-[10px] text-muted-foreground">
              {detail.tier && <span className="uppercase tracking-wider">{detail.tier}</span>}
              {detail.priority != null && <span>· priority {String(detail.priority)}</span>}
              {detail.driven_by && <span>· driven by {detail.driven_by}</span>}
              {(detail.tags || []).map((t) => <span key={t} className="rounded bg-secondary px-1.5 py-0">{t}</span>)}
            </div>
            {detail.description && <Section label="What this means"><p className="leading-relaxed text-foreground/90">{detail.description}</p></Section>}
            {detail.serves && <Section label="Why he's pursuing it"><p className="leading-relaxed text-foreground/85">↳ serves: {detail.serves}</p></Section>}
            {milestones.length > 0 && (
              <Section label={`How it's accomplished · ${metN}/${milestones.length} met`}>
                <ul className="space-y-1">
                  {milestones.map((m, i) => (
                    <li key={i} className="flex items-start gap-1.5">
                      {m.met ? <Check className="mt-0.5 h-3 w-3 shrink-0 text-signal-ok" /> : <Circle className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/50" />}
                      <span className={m.met ? "text-foreground/90" : "text-muted-foreground"}>{m.text}{m.met_at && <span className="ml-1 text-[10px] text-muted-foreground/60">· {fmtDateTime(m.met_at)}</span>}</span>
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {plan.length > 0 && (
              <Section label={`The work it planned · ${doneSteps}/${plan.length} steps done`}>
                <ol className="space-y-1">
                  {plan.map((p, i) => {
                    const done = /complet/i.test(p.status || "");
                    return (
                      <li key={i} className="flex items-start gap-1.5">
                        {done ? <Check className="mt-0.5 h-3 w-3 shrink-0 text-signal-ok" /> : <Circle className="mt-0.5 h-3 w-3 shrink-0 text-muted-foreground/50" />}
                        <span className={done ? "text-foreground/85" : "text-muted-foreground"}>{p.step}{p.status && <span className="ml-1 text-[10px] text-muted-foreground/60">· {p.status}</span>}</span>
                      </li>
                    );
                  })}
                </ol>
              </Section>
            )}
            {history.length > 0 && (
              <Section label="History">
                <ul className="space-y-0.5">
                  {history.map((h, i) => (
                    <li key={i} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                      <span className="h-1 w-1 rounded-full bg-muted-foreground/50" />
                      <span className="text-foreground/80">{h.event}</span>
                      {h.timestamp && <span className="ml-auto text-[10px] text-muted-foreground/60">{fmtDateTime(h.timestamp)}</span>}
                    </li>
                  ))}
                </ul>
              </Section>
            )}
            {detail.completed_timestamp && <div className="text-[10px] text-muted-foreground">Completed {fmtDateTime(detail.completed_timestamp)}</div>}
          </div>
        )}

        {tab === "produced" && (
          <div className="space-y-2">
            <p className="text-[10px] leading-snug text-muted-foreground">
              The actual long-memory entries he wrote during this goal{arts.kws.length > 0 && <> or about <span className="font-mono">{arts.kws.join(", ")}</span></>}. Each shows its <b>source</b> and time — what he really did, not the templated plan.
            </p>
            {arts.loading && <div className="text-[11px] text-muted-foreground">Correlating his memory…</div>}
            {!arts.loading && arts.list.length === 0 && (
              <div className="rounded-md border border-border bg-muted/30 px-2 py-3 text-center text-[11px] text-muted-foreground">No memory entries are linked to this goal yet.</div>
            )}
            {arts.list.map((a, i) => (
              <div key={a.id || i} className="rounded-md border border-border bg-muted/20 p-2">
                <div className="mb-1 flex items-center gap-1.5 text-[9px] text-muted-foreground">
                  <span className="rounded bg-secondary px-1.5 py-0 font-mono text-foreground/70">{a.event_type || "memory"}</span>
                  {a.on_topic && <span className="text-signal-ok">on-topic</span>}
                  {a.in_window && <span className="text-signal-info">during goal</span>}
                  <span className="ml-auto">{fmtDateTime(a.ts)}</span>
                </div>
                <p className="whitespace-pre-wrap text-[11px] leading-snug text-foreground/85">{a.content}</p>
              </div>
            ))}
          </div>
        )}

        {tab === "raw" && (
          <div className="space-y-1">
            <p className="text-[10px] text-muted-foreground">The complete stored record — every field, exactly as he wrote it.</p>
            <pre className="overflow-auto rounded bg-muted/40 p-2 text-[10px] leading-snug"><code className="font-mono">{JSON.stringify(detail.raw ?? detail, null, 2)}</code></pre>
          </div>
        )}
      </div>
    </div>
  );
}

function Section({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[9px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</div>
      {children}
    </div>
  );
}
