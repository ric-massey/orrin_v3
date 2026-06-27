import { useEffect, useMemo, useState } from "react";
import { Activity, Cpu, Database, HelpCircle, LayoutGrid, Radio, RotateCcw, X } from "lucide-react";
import { Responsive, useContainerWidth } from "react-grid-layout";
import "react-grid-layout/css/styles.css";
import { useTelemetryState } from "@/App";
import { useStreamStale } from "@/lib/telemetry";
import { API } from "@/lib/cognitive";
import { fetchJSON } from "@/lib/fetchJSON";
import { useLocalStorage } from "@/lib/useLocalStorage";
import CognitiveSphere from "@/components/brain/CognitiveSphere";
import AffectRings from "@/components/brain/AffectRings";
import MemoryInspector from "@/components/brain/MemoryInspector";
import LiveConsole from "@/components/brain/LiveConsole";
import MetricsStrip from "@/components/brain/MetricsStrip";
import GoalsPanel from "@/components/brain/GoalsPanel";
import ConsciousnessPanel from "@/components/brain/ConsciousnessPanel";
import VitalSignsRow from "@/components/brain/VitalSignsRow";
import BenchmarkPanel from "@/components/brain/BenchmarkPanel";
import GoalHealthPanel from "@/components/brain/GoalHealthPanel";
import InnerWeatherPanel from "@/components/brain/InnerWeatherPanel";
import SymbolicMindPanel from "@/components/brain/SymbolicMindPanel";
import PredictionsPanel from "@/components/brain/PredictionsPanel";
import DrivesPanel from "@/components/brain/DrivesPanel";
import LearningPanel from "@/components/brain/LearningPanel";
import TensionsPanel from "@/components/brain/TensionsPanel";
import HealthPanel from "@/components/brain/HealthPanel";
import SelfModelPanel from "@/components/brain/SelfModelPanel";
import RelationshipsPanel from "@/components/brain/RelationshipsPanel";
import DreamsPanel from "@/components/brain/DreamsPanel";
import LanguagePanel from "@/components/brain/LanguagePanel";
import type { LiveIntero } from "@/components/brain/DrivesPanel";
import { useLexicon } from "@/lib/lexicon";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "@/components/ErrorBoundary";

// ── Fix 3: moveable/resizable layout ─────────────────────────────────────────
// One react-grid-layout `Responsive` grid replaces the static CSS grids. Drag
// handle = each panel's CardHeader (`.card-drag`, set in ui/card.tsx); per-item
// min sizes keep panels above usefulness; the layout persists to localStorage
// (`orrin.brain.layout.v1`) and "Reset layout" restores this default — which
// mirrors the old static grid exactly.

type LayoutItem = { i: string; x: number; y: number; w: number; h: number; minW?: number; minH?: number };
type Layouts = Record<string, LayoutItem[]>;

const PANEL_IDS = [
  "sphere", "affect", "metrics", "memory",
  "consciousness", "goals", "console",
  "bench", "goalhealth", "weather", "symbolic", "predictions", "drives",
  "learning", "tensions", "health", "self", "relationships", "dreams", "language",
] as const;
type PanelId = (typeof PANEL_IDS)[number];

const DEEP_PANELS: PanelId[] = [
  "bench", "goalhealth", "weather", "symbolic", "predictions", "drives",
  "learning", "tensions", "health", "self", "relationships", "dreams", "language",
];

// rowHeight 30 + margin 16 → px height ≈ 46h − 16. h11≈490 (old 480px sphere),
// h9≈398 (old 380px deep boxes), h7≈306, h10≈444.
function defaultLayouts(): Layouts {
  const lg: LayoutItem[] = [
    { i: "sphere", x: 0, y: 0, w: 8, h: 11, minW: 5, minH: 7 },
    { i: "affect", x: 0, y: 11, w: 8, h: 7, minW: 4, minH: 5 },
    { i: "metrics", x: 0, y: 18, w: 8, h: 6, minW: 4, minH: 4 },
    { i: "memory", x: 0, y: 24, w: 8, h: 7, minW: 4, minH: 5 },
    { i: "consciousness", x: 8, y: 0, w: 4, h: 8, minW: 3, minH: 5 },
    { i: "goals", x: 8, y: 8, w: 4, h: 7, minW: 3, minH: 5 },
    { i: "console", x: 8, y: 15, w: 4, h: 10, minW: 3, minH: 5 },
    ...DEEP_PANELS.map((id, k) => ({
      i: id, x: (k % 3) * 4, y: 31 + Math.floor(k / 3) * 9, w: 4, h: 9, minW: 3, minH: 5,
    })),
  ];
  const md: LayoutItem[] = [
    { i: "sphere", x: 0, y: 0, w: 8, h: 11, minW: 4, minH: 7 },
    { i: "consciousness", x: 0, y: 11, w: 4, h: 8, minW: 3, minH: 5 },
    { i: "goals", x: 4, y: 11, w: 4, h: 8, minW: 3, minH: 5 },
    { i: "affect", x: 0, y: 19, w: 8, h: 7, minW: 4, minH: 5 },
    { i: "metrics", x: 0, y: 26, w: 8, h: 6, minW: 4, minH: 4 },
    { i: "memory", x: 0, y: 32, w: 4, h: 9, minW: 3, minH: 5 },
    { i: "console", x: 4, y: 32, w: 4, h: 9, minW: 3, minH: 5 },
    ...DEEP_PANELS.map((id, k) => ({
      i: id, x: (k % 2) * 4, y: 41 + Math.floor(k / 2) * 9, w: 4, h: 9, minW: 3, minH: 5,
    })),
  ];
  const sm: LayoutItem[] = PANEL_IDS.map((id, k) => ({
    i: id, x: 0, y: k * 9, w: 6, h: id === "sphere" ? 11 : 9, minW: 3, minH: 5,
  }));
  return { lg, md, sm };
}

// Columns per breakpoint (mirror the <Responsive cols> prop). Used to clamp a
// stored layout back inside the grid so a panel can't be stranded off-screen.
const COLS: Record<string, number> = { lg: 12, md: 8, sm: 6 };

// A stored layout from an older release may miss panels added since (or carry
// removed ones) — sanitize back to defaults rather than render a broken grid.
function sanitizeLayouts(raw: unknown): Layouts {
  const def = defaultLayouts();
  if (!raw || typeof raw !== "object") return def;
  const out: Layouts = {};
  for (const bp of ["lg", "md", "sm"]) {
    const items = (raw as Record<string, unknown>)[bp];
    if (!Array.isArray(items)) return def;
    const ids = new Set(items.map((it) => (it as LayoutItem)?.i));
    if (PANEL_IDS.some((id) => !ids.has(id))) return def;
    const cols = COLS[bp] ?? 12;
    out[bp] = items
      .filter(
        (it): it is LayoutItem =>
          !!it && typeof (it as LayoutItem).i === "string" &&
          PANEL_IDS.includes((it as LayoutItem).i as PanelId) &&
          [(it as LayoutItem).x, (it as LayoutItem).y, (it as LayoutItem).w, (it as LayoutItem).h]
            .every((n) => typeof n === "number" && isFinite(n)),
      )
      // L5: clamp each item inside the grid. A panel dragged/resized off the
      // right edge (or to an absurd offset) stays recoverable without needing a
      // full layout reset.
      .map((it) => {
        const minW = it.minW ?? 1;
        const minH = it.minH ?? 1;
        const w = Math.min(Math.max(it.w, minW), cols);
        const x = Math.min(Math.max(0, it.x), Math.max(0, cols - w));
        return { ...it, w, x, y: Math.max(0, it.y), h: Math.max(it.h, minH) };
      });
  }
  return out;
}

export default function Brain() {
  const t = useTelemetryState();
  const { t: lx, tip: lxTip } = useLexicon();

  // The old "Memory records" KPI counted live ops seen this session and
  // presented it as its memory count (Fix 8). Show the REAL long-term store
  // size instead; fall back to the live-op count until the endpoint answers.
  const [longTermCount, setLongTermCount] = useState<number | null>(null);
  useEffect(() => {
    let stop = false;
    const load = () =>
      fetchJSON<{ counts?: Record<string, number> }>(`${API}/memory_counts`)
        .then((d) => { if (!stop && d.counts && typeof d.counts.long === "number") setLongTermCount(d.counts.long); })
        .catch(() => {});
    load();
    const id = setInterval(load, 30_000);
    return () => { stop = true; clearInterval(id); };
  }, []);

  // Fix 9 / M1: the socket can claim to be open while frames stopped arriving —
  // go amber when the last telemetry update is old. Shared with the Header so
  // both agree (the hook's own tick keeps this honest with no frames arriving).
  const streamStale = useStreamStale(t);

  // Fix 11: one-time orientation overlay; the "Tour" button re-opens it.
  const [welcomeSeen, setWelcomeSeen] = useLocalStorage<boolean>("orrin.brain.welcome.v1", false, { sanitize: (r) => !!r });

  // Fix 3: user-arrangeable layout, persisted; Reset restores the default grid.
  const [layouts, setLayouts] = useLocalStorage<Layouts>("orrin.brain.layout.v1", defaultLayouts(), { sanitize: sanitizeLayouts });
  const { width, containerRef, mounted } = useContainerWidth();

  const resetPanel = (id: PanelId) => {
    const defaults = defaultLayouts();
    setLayouts((current) => {
      const next: Layouts = {};
      for (const bp of ["lg", "md", "sm"]) {
        const fallback = defaults[bp].find((item) => item.i === id);
        next[bp] = current[bp].map((item) =>
          item.i === id && fallback ? { ...fallback } : item,
        );
      }
      return sanitizeLayouts(next);
    });
  };

  // On phones the panels stack single-column and touch-dragging a card header
  // fights page scrolling, so arranging is desktop/tablet-only.
  const isPhone = width > 0 && width < 640;

  // Panel registry — ids must match PANEL_IDS / defaultLayouts.
  const panels = useMemo<Record<PanelId, React.ReactNode>>(() => ({
    sphere: <CognitiveSphere telemetry={t} />,
    affect: <AffectRings affect={t.affect} />,
    metrics: <MetricsStrip telemetry={t} />,
    memory: <MemoryInspector telemetry={t} />,
    consciousness: <ConsciousnessPanel telemetry={t} />,
    goals: <GoalsPanel telemetry={t} />,
    console: <LiveConsole telemetry={t} />,
    bench: <BenchmarkPanel />,
    goalhealth: <GoalHealthPanel />,
    weather: <InnerWeatherPanel />,
    symbolic: <SymbolicMindPanel />,
    predictions: <PredictionsPanel />,
    drives: <DrivesPanel live={t.interoception as LiveIntero | null} />,
    learning: <LearningPanel />,
    tensions: <TensionsPanel />,
    health: <HealthPanel />,
    self: <SelfModelPanel />,
    relationships: <RelationshipsPanel />,
    dreams: <DreamsPanel />,
    language: <LanguagePanel />,
  }), [t]);

  return (
    <div className="grid-bg min-h-[calc(100dvh-3.5rem)] sm:min-h-[calc(100dvh-4rem)]">
      <div className="mx-auto max-w-[1600px] p-3 sm:p-4">
        {/* KPI strip */}
        <div className="mb-4 grid grid-cols-2 gap-2 sm:gap-3 lg:grid-cols-4">
          <Kpi icon={<Cpu className="h-4 w-4" />} label={lx("kpi_stage")} title={lxTip("kpi_stage")} value={t.activeNode ?? "—"} accent />
          <Kpi icon={<Activity className="h-4 w-4" />} label={lx("kpi_cycle")} value={String(t.cycle)} />
          <Kpi
            icon={<Radio className="h-4 w-4" />}
            label={lx("kpi_stream")}
            title={lxTip("kpi_stream")}
            value={
              t.source === "stopped" ? "Stopped"
              : streamStale ? "Stalled"
              : t.source === "live" ? "Live"
              : t.source === "demo" ? "Demo"
              : t.retries > 0 ? `Reconnecting (${t.retries})`
              : "Connecting"
            }
            warn={streamStale}
          />
          <Kpi
            icon={<Database className="h-4 w-4" />}
            label={longTermCount != null ? lx("kpi_longterm") : lx("kpi_memops")}
            title={lxTip(longTermCount != null ? "kpi_longterm" : "kpi_memops")}
            value={String(longTermCount ?? t.memory.length)}
          />
        </div>

        {/* L0 vital-signs row — one chip per subsystem, computed server-side
            by /api/resources on a single 10s timer; click a chip to jump to its
            box (UI_FIXES §new-surfaces). */}
        <div className="flex flex-wrap items-start gap-2">
          <div className="min-w-0 flex-1 basis-full sm:basis-0">
            <VitalSignsRow />
          </div>
          {!isPhone && (
            <button
              onClick={() => setLayouts(defaultLayouts())}
              className="mt-0.5 flex flex-none items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground shadow-sm hover:text-foreground"
              title="Restore the default panel arrangement. Drag a panel by its header; resize from its corner."
            >
              <LayoutGrid className="h-3.5 w-3.5" /> Reset layout
            </button>
          )}
          <button
            onClick={() => setWelcomeSeen(false)}
            className="mt-0.5 flex flex-none items-center gap-1 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground shadow-sm hover:text-foreground"
            title="What am I looking at? Re-open the orientation."
          >
            <HelpCircle className="h-3.5 w-3.5" /> Tour
          </button>
        </div>

        {/* First-visit orientation (Fix 11) — dismissible, localStorage-keyed. */}
        {!welcomeSeen && <WelcomeOverlay onClose={() => setWelcomeSeen(true)} />}

        {/* Fix 3: ONE draggable/resizable grid holds every panel (main +
            deep-telemetry surfaces). Drag handle = the card header
            (`.card-drag`); interactive header controls are excluded via
            dragConfig.cancel so ℹ️/tabs/filters still click. Layout persists
            per breakpoint; "Reset layout" restores the pre-Fix-3 arrangement. */}
        <div ref={containerRef as React.RefObject<HTMLDivElement>} className="-mx-2">
          {mounted && (
            <Responsive
              layouts={layouts}
              breakpoints={{ lg: 1100, md: 800, sm: 0 }}
              cols={{ lg: 12, md: 8, sm: 6 }}
              rowHeight={30}
              margin={[16, 16]}
              containerPadding={[8, 8]}
              width={width}
              dragConfig={{
                enabled: !isPhone,
                handle: ".card-drag",
                cancel: "button, a, input, select, textarea, [role=button], [role=tab]",
              }}
              resizeConfig={{ enabled: !isPhone, handles: ["se"] }}
              onLayoutChange={(_l, all) => setLayouts(sanitizeLayouts(all))}
            >
              {PANEL_IDS.map((id) => (
                <div key={id} className="group/panel relative overflow-auto">
                  {!isPhone && (
                    <button
                      type="button"
                      onClick={() => resetPanel(id)}
                      className="absolute right-2 top-2 z-20 grid h-7 w-7 place-items-center rounded-md border border-border bg-card/95 text-muted-foreground opacity-0 shadow-sm transition hover:text-foreground focus:opacity-100 group-hover/panel:opacity-100"
                      title={`Reset the ${id} panel position and size`}
                      aria-label={`Reset ${id} panel`}
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  )}
                  {/* H5: isolate each panel — a malformed data shape that throws
                      in one box degrades that box, instead of white-screening
                      the entire dashboard (the least-visible failure mode). */}
                  <ErrorBoundary fallback={<PanelError id={id} />}>
                    {panels[id]}
                  </ErrorBoundary>
                </div>
              ))}
            </Responsive>
          )}
        </div>
      </div>
    </div>
  );
}

// First-visit orientation (Fix 11): six lines that make the page legible in a
// minute, no tour library — one absolutely-positioned panel.
function WelcomeOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm" onClick={onClose}>
      <div
        className="max-h-[80vh] w-full max-w-lg overflow-auto rounded-xl border border-border bg-card p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Dashboard orientation"
      >
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-base font-semibold">This is Orrin's runtime, live.</h2>
          <button onClick={onClose} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label="Close">
            <X className="h-4 w-4" />
          </button>
        </div>
        <ol className="list-decimal space-y-2 pl-5 text-[13px] leading-relaxed text-foreground/90">
          <li>It runs in ~20-second <strong>cycles</strong>. The <strong>Function-call graph</strong> is every cognitive function it can run — the bright comet is what's running this cycle; the amber pulse is the background task runner advancing a goal step.</li>
          <li><strong>Attention arbitration</strong> is what won the broadcast this cycle — and what almost won, ranked beneath it. The Stream tab is the recorded workspace broadcast log.</li>
          <li><strong>Control signals</strong> and <strong>Metrics</strong> are the internal signal state, now and over time. Every number has an ℹ️ that explains it down to the code that computes it.</li>
          <li><strong>Memory</strong> has two views: the live ticker of reads/writes, and the real stores on disk you can browse and search.</li>
          <li>The <strong>chip row</strong> up top is the subsystem status strip — one chip per subsystem, click any to jump to its box. The boxes below the main grid go deep: benchmarks, goal-closure metrics, the internal clock estimate, the symbolic rule engine, predictions, priority weights, learning, conflict state, and system health.</li>
          <li>Everything is honest by design: stale panels say <em>stale</em>, failing benchmarks say <em>FAIL</em>, and one thing is deliberately absent — the protected interior, which this dashboard does not read.</li>
        </ol>
        <button
          onClick={onClose}
          className="mt-4 w-full rounded-md bg-foreground/10 px-3 py-1.5 text-[13px] font-medium hover:bg-foreground/15"
        >
          Got it — show me the runtime
        </button>
      </div>
    </div>
  );
}

// H5 fallback: rendered in place of a panel that threw, so the failure is
// visible and localized rather than a blank page.
function PanelError({ id }: { id: string }) {
  return (
    <div
      role="alert"
      className="flex h-full min-h-[120px] flex-col items-center justify-center gap-1 rounded-xl border border-signal-warn/40 bg-signal-warn/5 p-4 text-center"
    >
      <div className="text-[12px] font-medium text-signal-warn">This panel failed to render</div>
      <div className="text-[11px] text-muted-foreground">
        <span className="font-mono">{id}</span> — its data may be malformed. Other panels are unaffected.
      </div>
      <button
        onClick={() => window.location.reload()}
        className="mt-1 rounded-md border border-border bg-card px-2 py-0.5 text-[11px] text-muted-foreground hover:text-foreground"
      >
        Reload
      </button>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  accent,
  warn,
  title,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  accent?: boolean;
  warn?: boolean;
  title?: string;
}) {
  return (
    <div title={title} className={cn("flex items-center gap-2.5 rounded-xl border bg-card px-3 py-2.5 shadow-sm sm:gap-3 sm:px-4 sm:py-3", warn && "border-signal-warn/50")}>
      <span
        className={cn(
          "flex h-8 w-8 flex-none items-center justify-center rounded-lg sm:h-9 sm:w-9",
          warn ? "bg-signal-warn/15 text-signal-warn" : accent ? "bg-signal-accent/15 text-signal-accent" : "bg-secondary text-muted-foreground"
        )}
      >
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
        <div className="truncate text-lg font-semibold capitalize tabular-nums">{value}</div>
      </div>
    </div>
  );
}
