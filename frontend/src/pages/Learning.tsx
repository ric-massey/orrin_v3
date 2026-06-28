import { ArrowRight, GitBranch, Repeat2, Target, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { usePolledJSON } from "@/lib/usePolled";

// Learning (UI master plan §5.1): the behavior-change log. The dashboard is strong at
// STOCKS (counts that exist now) and weak at FLOWS (what changed and why). This room
// answers "is it actually learning?" by rendering each self-edit the adaptation engine
// makes as a before → after → because diff. The engine (behavioral_adaptation.py) has
// always rewritten behaviour; until now nothing surfaced the rewrite.

interface Change {
  when?: string;
  pattern?: string;
  situation?: string;
  old_action?: string;
  new_action?: string;
  reason?: string;
  evidence?: string;
}
interface Feed {
  changes?: Change[];
  total?: number;
  by_pattern?: Record<string, number>;
}
interface BeliefRevision {
  kind?: string;
  timestamp?: string;
  subject?: string;
  summary?: string;
  old_confidence?: number | null;
  new_confidence?: number | null;
  confidence_delta?: number | null;
  evidence_count?: number;
  source?: string;
  status?: string;
}
interface BeliefFeed {
  revisions?: BeliefRevision[];
  total?: number;
  churn?: Record<string, { count?: number; strengthened?: number; weakened?: number; unchanged?: number }>;
}
interface GoalProgressRow {
  id?: string;
  title?: string;
  status?: string;
  tier?: string;
  milestones_met?: number;
  milestones_total?: number;
  steps_done?: number;
  steps_total?: number;
  progress?: number | null;
}
interface LearningStatus {
  goal_progress?: {
    goals?: GoalProgressRow[];
    total?: number;
    milestones_met?: number;
    milestones_total?: number;
  };
  rut?: {
    function?: string;
    score?: number;
    top_count?: number;
    window?: number;
    threshold?: number;
    consecutive_function?: string;
    consecutive?: number;
  };
}

// A plain-language name + accent per pattern type, so the log reads as behaviour, not
// internal jargon. Keys mirror _classify() in behavioral_adaptation.py.
const PATTERN_META: Record<string, { label: string; tone: string }> = {
  rut: { label: "Stuck in a rut", tone: "text-signal-warn" },
  oscillation: { label: "Flip-flopping", tone: "text-signal-warn" },
  goal_avoidance: { label: "Avoiding a goal", tone: "text-signal-error" },
  reflection_imbalance: { label: "Over-thinking", tone: "text-signal-error" },
  emotional_stagnation: { label: "Signals stuck", tone: "text-signal-warn" },
};

export default function Learning() {
  const feed = usePolledJSON<Feed>("/api/behavior-changes?n=60");
  const beliefs = usePolledJSON<BeliefFeed>("/api/belief-revisions?n=80");
  const learning = usePolledJSON<LearningStatus>("/api/learning?n=10");
  const changes = feed?.changes ?? [];
  const byPattern = feed?.by_pattern ?? {};
  const revisions = beliefs?.revisions ?? [];
  const patternRows = Object.entries(byPattern)
    .filter(([, n]) => n > 0)
    .sort((a, b) => b[1] - a[1]);
  const churnRows = Object.entries(beliefs?.churn ?? {})
    .filter(([, rec]) => Number(rec.count ?? 0) > 0)
    .sort((a, b) => Number(b[1].count ?? 0) - Number(a[1].count ?? 0));

  return (
    <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-6 sm:px-6">
      <div className="space-y-1">
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
          <TrendingUp className="h-5 w-5 text-primary" />
          How its behaviour is changing
        </h1>
        <p className="text-sm text-muted-foreground">
          Every time Orrin detects a pattern in its own activity — a rut, avoidance,
          over-processing — the adaptation engine rewrites how it acts. Each rewrite is
          logged here as before&nbsp;→&nbsp;after&nbsp;→&nbsp;because. This is the honest
          answer to "is it actually learning?".
        </p>
      </div>

      {patternRows.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {patternRows.map(([p, n]) => (
            <span
              key={p}
              className="rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground"
            >
              <span className={PATTERN_META[p]?.tone ?? "text-foreground"}>
                {PATTERN_META[p]?.label ?? p}
              </span>
              <span className="ml-1.5 tabular-nums">{n}</span>
            </span>
          ))}
        </div>
      )}

      {changes.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
            {feed == null
              ? "Loading…"
              : "No behaviour changes yet — no ruts, avoidance, or imbalance have been detected this run."}
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-3">
          {changes.map((c, i) => (
            <ChangeCard key={`${c.when ?? ""}-${i}`} c={c} />
          ))}
        </ul>
      )}

      <section className="grid gap-3 border-t pt-5 md:grid-cols-2">
        <GoalProgressCard progress={learning?.goal_progress} />
        <RutCard rut={learning?.rut} />
      </section>

      <section className="space-y-3 border-t pt-5">
        <div className="space-y-1">
          <h2 className="flex items-center gap-2 text-base font-semibold tracking-tight">
            <GitBranch className="h-4 w-4 text-primary" />
            What beliefs moved
          </h2>
          <p className="text-sm text-muted-foreground">
            Self-beliefs, opinions, and symbolic rules in one time-ordered feed, with
            confidence movement and evidence counts where the source log records them.
          </p>
        </div>

        {churnRows.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {churnRows.map(([kind, rec]) => (
              <span
                key={kind}
                className="rounded-full border bg-card px-2.5 py-1 text-xs text-muted-foreground"
              >
                <span className="font-medium text-foreground">{kindLabel(kind)}</span>
                <span className="ml-1.5 tabular-nums">{rec.count ?? 0}</span>
                <span className="ml-1.5 text-signal-ok tabular-nums">+{rec.strengthened ?? 0}</span>
                <span className="ml-1 text-signal-error tabular-nums">-{rec.weakened ?? 0}</span>
              </span>
            ))}
          </div>
        )}

        {revisions.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm italic text-muted-foreground">
              {beliefs == null
                ? "Loading…"
                : "No belief revisions have been recorded yet."}
            </CardContent>
          </Card>
        ) : (
          <ul className="space-y-3">
            {revisions.map((r, i) => (
              <BeliefCard key={`${r.kind ?? ""}-${r.timestamp ?? ""}-${i}`} r={r} />
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function GoalProgressCard({ progress }: { progress?: LearningStatus["goal_progress"] }) {
  const goals = progress?.goals ?? [];
  const met = progress?.milestones_met ?? 0;
  const total = progress?.milestones_total ?? 0;
  const pct = total > 0 ? met / total : 0;
  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Target className="h-4 w-4 text-primary" />
            Goal progress
          </h2>
          <span className="text-xs tabular-nums text-muted-foreground">{progress?.total ?? 0} tracked</span>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>Milestones met</span>
            <span className="tabular-nums">{met}/{total}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-secondary">
            <div className="h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, pct * 100))}%` }} />
          </div>
        </div>
        {goals.length === 0 ? (
          <p className="text-sm italic text-muted-foreground">No goal milestones are visible yet.</p>
        ) : (
          <div className="space-y-2">
            {goals.slice(0, 4).map((g, i) => (
              <div key={`${g.id ?? g.title ?? ""}-${i}`}>
                <div className="mb-0.5 flex items-center gap-2 text-xs">
                  <span className="min-w-0 flex-1 truncate font-medium">{g.title}</span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">{goalDone(g)}</span>
                </div>
                <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
                  <div className="h-full rounded-full bg-signal-ok" style={{ width: `${Math.max(0, Math.min(100, Number(g.progress ?? 0) * 100))}%` }} />
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function RutCard({ rut }: { rut?: LearningStatus["rut"] }) {
  const score = Number(rut?.score ?? 0);
  const threshold = Number(rut?.threshold ?? 0.75);
  const hot = score >= threshold;
  return (
    <Card>
      <CardContent className="space-y-3 py-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Repeat2 className={`h-4 w-4 ${hot ? "text-signal-error" : "text-primary"}`} />
            Rut readout
          </h2>
          <span className={hot ? "text-xs font-medium text-signal-error" : "text-xs text-muted-foreground"}>
            {hot ? "rut pressure" : "varied"}
          </span>
        </div>
        <div>
          <div className="mb-1 flex justify-between text-xs text-muted-foreground">
            <span>{rut?.function || "no function"}</span>
            <span className="tabular-nums">{rut?.top_count ?? 0}/{rut?.window ?? 0}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-secondary">
            <div className={hot ? "h-full rounded-full bg-signal-error" : "h-full rounded-full bg-primary"} style={{ width: `${Math.max(0, Math.min(100, score * 100))}%` }} />
          </div>
        </div>
        <p className="text-xs leading-relaxed text-muted-foreground">
          Current streak: <span className="font-medium text-foreground">{rut?.consecutive_function || "—"}</span>
          <span className="tabular-nums"> ×{rut?.consecutive ?? 0}</span>. Rut threshold is {Math.round(threshold * 100)}% of the recent window.
        </p>
      </CardContent>
    </Card>
  );
}

function ChangeCard({ c }: { c: Change }) {
  const meta = c.pattern ? PATTERN_META[c.pattern] : undefined;
  return (
    <li>
      <Card>
        <CardContent className="space-y-3 py-4">
          <div className="flex items-center justify-between gap-2">
            <span className={`text-sm font-medium ${meta?.tone ?? "text-foreground"}`}>
              {meta?.label ?? c.pattern ?? "Adjustment"}
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">{relTime(c.when)}</span>
          </div>

          {c.situation && (
            <p className="text-sm text-muted-foreground">
              <span className="text-foreground">Noticed:</span> {c.situation}
            </p>
          )}

          {/* The before → after diff — the whole point of the room. */}
          <div className="flex flex-col gap-2 rounded-lg border bg-muted/30 p-3 sm:flex-row sm:items-center">
            <div className="flex-1 text-sm">
              <Label>Before</Label>
              <span className="text-muted-foreground">{c.old_action || "—"}</span>
            </div>
            <ArrowRight className="hidden h-4 w-4 shrink-0 text-muted-foreground sm:block" />
            <div className="flex-1 text-sm">
              <Label>After</Label>
              <span className="text-foreground">{c.new_action || "—"}</span>
            </div>
          </div>

          {c.reason && (
            <p className="text-xs leading-relaxed text-muted-foreground">
              <span className="font-medium text-foreground">Because:</span> {c.reason}
            </p>
          )}
        </CardContent>
      </Card>
    </li>
  );
}

function BeliefCard({ r }: { r: BeliefRevision }) {
  const delta = Number(r.confidence_delta ?? 0);
  const deltaKnown = r.confidence_delta != null && Number.isFinite(delta);
  const confidence =
    r.old_confidence != null && r.new_confidence != null
      ? `${fmtConf(r.old_confidence)} → ${fmtConf(r.new_confidence)}`
      : r.new_confidence != null
        ? fmtConf(r.new_confidence)
        : "—";
  return (
    <li>
      <Card>
        <CardContent className="space-y-2 py-4">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium uppercase text-muted-foreground">
                  {kindLabel(r.kind)}
                </span>
                <span className="truncate text-sm font-medium">{r.subject || "belief"}</span>
              </div>
              {r.summary && (
                <p className="mt-1 line-clamp-3 text-sm leading-relaxed text-muted-foreground">
                  {r.summary}
                </p>
              )}
            </div>
            <span className="shrink-0 text-xs text-muted-foreground">{relTime(r.timestamp)}</span>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>
              <Label>Confidence</Label>
              <span className="tabular-nums text-foreground">{confidence}</span>
            </span>
            {deltaKnown && (
              <span className={delta >= 0 ? "text-signal-ok" : "text-signal-error"}>
                {delta >= 0 ? "+" : ""}
                {delta.toFixed(2)}
              </span>
            )}
            <span>
              <Label>Evidence</Label>
              <span className="tabular-nums">{r.evidence_count ?? 0}</span>
            </span>
            {r.status && <span>{r.status}</span>}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

const Label = ({ children }: { children: React.ReactNode }) => (
  <span className="mr-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">
    {children}
  </span>
);

// ISO-8601 → compact relative time. Falls back to the raw string if unparseable.
function relTime(when?: string): string {
  if (!when) return "";
  const t = Date.parse(when);
  if (!Number.isFinite(t)) return when;
  const secs = (Date.now() - t) / 1000;
  if (secs < 60) return "just now";
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return new Date(t).toLocaleDateString();
}

function fmtConf(n: number): string {
  return Number(n).toFixed(2);
}

function kindLabel(kind?: string): string {
  if (kind === "symbolic_rule") return "symbolic rule";
  if (kind === "self") return "self-belief";
  return kind || "belief";
}

function goalDone(g: GoalProgressRow): string {
  if (Number(g.milestones_total ?? 0) > 0) return `${g.milestones_met ?? 0}/${g.milestones_total ?? 0}`;
  if (Number(g.steps_total ?? 0) > 0) return `${g.steps_done ?? 0}/${g.steps_total ?? 0}`;
  return g.status || "—";
}
