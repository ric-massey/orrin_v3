// Client-side telemetry view-model — the MERGED, complete state the UI renders
// (always populated from initialState, so e.g. affect.valence / goal.title are
// non-optional here even though they are optional on the wire).
//
// The WIRE contract (the partial frames that actually cross the socket) is NOT
// hand-authored here anymore: it lives in `./telemetry.gen.ts`, generated from
// backend/server/schema.py (`make telemetry-types`) and validated at runtime in
// telemetry.ts. These view-types are the post-merge projection of that contract.
// Pure types + domain constants, kept separate from the runtime hook (telemetry.ts).

import type { LlmCost } from "./telemetry.gen";
export type { LlmCost };

export const LOOP_NODES = ["perceive", "reflect", "plan", "act"] as const;
export type LoopNode = (typeof LOOP_NODES)[number];
export type NodeStatus = "idle" | "active" | "done";
export type LogLevel = "debug" | "info" | "warn" | "error" | "critical";

export interface Affect {
  valence: number;
  arousal: number;
  homeostasis: number;
  extra: Record<string, number>;
}

export interface MemoryRecord {
  id?: string;
  op: "read" | "write";
  store: string;
  key: string;
  summary: string;
  salience?: number;
  ts?: number;
}

export interface LogLine {
  level: LogLevel;
  source: string;
  message: string;
  ts?: number;
}

export interface MetricPoint {
  t: number;
  [k: string]: number;
}

export interface Goal {
  id?: string;
  title: string;
  status: string;
  tier?: string;
  priority?: number | string | null;
  tags?: string[];
  steps_done?: number;
  steps_total?: number;
  current_step?: string | null;
  active?: boolean;
  serves?: string;
  aspiration?: boolean;
}

/** One node in the cognitive map (a registered function). */
export interface CatalogFn {
  name: string;
  subsystem: string;
  file: string;
  lineno: number;
  endline?: number;
  summary?: string;
  kind?: string;
  count?: number;
  avg_reward?: number;
}

export interface FnEdge {
  from: string;
  to: string;
  weight: number;
}

export interface FnCatalog {
  functions: Record<string, CatalogFn>;
  subsystems: Record<string, string[]>;
  edges?: FnEdge[];
}

/** A recent firing of a cognitive function (drives the map's "active light"). */
export interface FnEvent {
  fn: string;
  cycle?: number;
  reward?: number | null;
  /** Which cognitive lane ran it: "deliberate" (conscious slot) | "executive". */
  lane?: string;
}

// ── Dual-process / Global Workspace (§19 Consciousness panel) ───────────────
/** The single conscious content the Global Workspace broadcast this cycle. */
export interface WorkspaceConscious {
  content?: string;
  source?: string;       // user · affect · signal · goal · monitor …
  salience?: number;     // 0..1 competition winner score
  kind?: string;         // breakthrough kind, when the winner came from the Monitor
  wants?: string;        // route the Monitor asked the deliberate mind to take
  object?: string;
  facets?: Record<string, unknown>;
  members?: string[];
  referent_links?: string[];
  ts?: number;
}
/** A candidate the Monitor offered to the workspace (it never seizes the slot).
 *  `threshold` is the learned per-kind salience bias from §20.1 dismissal-
 *  recalibration: <1.0 means this kind has been "crying wolf" and is being quieted. */
export interface Breakthrough { kind: string; salience: number; wants?: string; threshold?: number }
/** Dumb structural watchdog row — fires on stall regardless of the Monitor (I12). */
export interface WatchdogRow { goal_id: string; cycles_since_advance: number; armed: boolean }
/** The Executive lane's backgrounded plan-step advance (the "dribble"). */
export interface ExecutiveSummary {
  active_fn?: string | null;
  active_step?: string | null;
  goal_id?: string | null;
  goal_title?: string;
  last_result?: { goal?: string; step?: string; [k: string]: unknown } | null;
  queue?: { goal_id?: string | null; title?: string; status?: string; next_step?: string | null }[];
  /** Multi-goal pursuit: every goal the Executive advanced THIS tick (the
   *  data behind the Sphere's K executive lights). */
  advanced?: { goal_id?: string | null; goal_title?: string; step?: string | null; fn?: string | null; status?: string }[];
  [k: string]: unknown;
}
export interface MonitorBlock { recent_breakthroughs?: Breakthrough[]; watchdog?: WatchdogRow[] }
/** A ranked candidate that competed for the workspace this cycle (Fix 4 —
 *  the "losers": what almost became conscious, and why this won). */
export interface WorkspaceCandidate { source?: string; content?: string; salience?: number; kind?: string; wants?: string; object?: string; facets?: Record<string, unknown>; members?: string[] }
export interface WorkspaceBlock { conscious?: WorkspaceConscious; candidates?: WorkspaceCandidate[] }

/** P7/A1 — the curated lived-surface projection (brain/loop/lived_surface.py).
 *  Felt language only; every field degrades to ""/[] rather than raw keys. */
export interface LivedSurface {
  attending_to: string;
  pressured_by: string[];
  what_changed: string;
  avoiding: string;
  trying_to_resolve: string;
}

/** The merged client-side view of the system, produced by useTelemetry(). */
export interface TelemetryState {
  activeNode: string | null;
  nodeStatus: Record<string, NodeStatus>;
  narrative: string;
  affect: Affect;
  memory: MemoryRecord[];
  logs: LogLine[];
  metrics: Record<string, number>;
  metricSeries: MetricPoint[];
  goals: Goal[];
  cycle: number;
  activeFn: string | null;
  /** Lane of the deliberate "active light": deliberate | executive (Gap 3). */
  activeLane: string | null;
  fnRecent: FnEvent[];
  // Dual-process §19 blocks (Consciousness panel). Null until first emitted.
  executive: ExecutiveSummary | null;
  monitor: MonitorBlock | null;
  workspace: WorkspaceBlock | null;
  /** Live interoceptive cost model, per executed function (Fix 7). */
  interoception: Record<string, unknown> | null;
  /** LLM-cost telemetry: reasoning-cache health + symbolic-vs-LLM ratio. */
  llmCost: LlmCost | null;
  /** P7/A1 curated lived surface: what it's like to be him right now. */
  lived: LivedSurface | null;
  /** Free-form extras the loop pushes (e.g. awareness). */
  extra: Record<string, unknown>;
  connected: boolean;
  /** "stopped" = the user shut Orrin down from the UI (an intentional offline
   *  state), distinct from "connecting" (couldn't reach / lost the backend). */
  source: "connecting" | "live" | "demo" | "stopped";
  /** Consecutive failed reconnect attempts (0 when live). Drives the
   *  "Reconnecting" indicator so a long outage isn't an indefinite "Connecting". */
  retries: number;
  updatedAt: number;
}
