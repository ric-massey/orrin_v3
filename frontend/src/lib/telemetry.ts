import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { LogLevel, LOOP_NODES, MetricPoint, TelemetryState } from "./types";
import { getTransport } from "./transport";
import { TelemetryFrameSchema } from "./telemetry.gen";

// Re-export the data contracts so existing `@/lib/telemetry` imports keep working.
export * from "./types";

// ── Boundary validation (Phase 5.2) ─────────────────────────────────────────
// Telemetry crosses a process + language boundary, so a malformed/version-skewed
// frame is checked against the generated wire contract (telemetry.gen.ts, itself
// generated from backend/server/schema.py) the moment it arrives — before it can
// corrupt UI state downstream. Non-fatal by design (a dropped chart point must
// never blank the whole UI): we warn loudly and still apply the frame. Warnings
// are capped so a persistent mismatch can't flood the console.
let _contractWarnings = 0;
function checkFrame(frame: unknown, kind: "snapshot" | "delta"): void {
  const r = TelemetryFrameSchema.safeParse(frame);
  if (!r.success && _contractWarnings < 25) {
    _contractWarnings += 1;
    console.warn(
      `[telemetry] ${kind} frame violates the wire contract (schema.py); applying anyway:`,
      r.error.issues.slice(0, 5),
    );
  }
}

const MEM_CAP = 500;
const LOG_CAP = 500; // cap the console ring to prevent browser memory bloat
const SERIES_CAP = 240;

export const initialState: TelemetryState = {
  activeNode: null,
  nodeStatus: { perceive: "idle", reflect: "idle", plan: "idle", act: "idle" },
  narrative: "Waiting for telemetry…",
  affect: { valence: 0.5, arousal: 0.3, homeostasis: 0.8, extra: {} },
  memory: [],
  logs: [],
  metrics: {},
  metricSeries: [],
  goals: [],
  cycle: 0,
  activeFn: null,
  activeLane: null,
  fnRecent: [],
  executive: null,
  monitor: null,
  workspace: null,
  interoception: null,
  llmCost: null,
  extra: {},
  connected: false,
  source: "connecting",
  retries: 0,
  updatedAt: 0,
};

// ─────────────────────────────────────────────────────────────────────────────
// Reducer
// ─────────────────────────────────────────────────────────────────────────────
type Action =
  | { type: "snapshot"; state: any }
  | { type: "delta"; frame: any }
  | { type: "status"; connected: boolean; source: TelemetryState["source"]; retries?: number }
  | { type: "reset" };

function applyDelta(s: TelemetryState, f: any): TelemetryState {
  const next: TelemetryState = { ...s };
  if (f.narrative != null) next.narrative = f.narrative;
  if (f.cycle != null) next.cycle = f.cycle;
  if (f.active_node != null) next.activeNode = f.active_node;
  if (f.node_status) next.nodeStatus = { ...s.nodeStatus, ...f.node_status };
  if (f.affect) {
    next.affect = {
      ...s.affect,
      ...f.affect,
      extra: { ...s.affect.extra, ...(f.affect.extra || {}) },
    };
  }
  if (f.metrics) next.metrics = { ...s.metrics, ...f.metrics };
  if (f.metric_point) next.metricSeries = [...s.metricSeries, f.metric_point].slice(-SERIES_CAP);
  if (Array.isArray(f.memory) && f.memory.length) {
    next.memory = [...s.memory, ...f.memory].slice(-MEM_CAP);
  }
  if (Array.isArray(f.logs) && f.logs.length) {
    next.logs = [...s.logs, ...f.logs].slice(-LOG_CAP);
  }
  if (Array.isArray(f.goals)) next.goals = f.goals;
  if (f.active_fn != null) next.activeFn = f.active_fn;
  if (f.active_lane != null) next.activeLane = f.active_lane;
  if (Array.isArray(f.fn_recent)) next.fnRecent = f.fn_recent;
  // Dual-process §19 blocks (latest-wins).
  if (f.executive != null) next.executive = f.executive;
  if (f.monitor != null) next.monitor = f.monitor;
  if (f.workspace != null) next.workspace = f.workspace;
  if (f.interoception != null) next.interoception = f.interoception;
  if (f.llm_cost != null) next.llmCost = f.llm_cost;
  if (f.extra != null) next.extra = { ...s.extra, ...f.extra };
  next.updatedAt = Date.now();
  return next;
}

function reducer(s: TelemetryState, a: Action): TelemetryState {
  switch (a.type) {
    case "status":
      return { ...s, connected: a.connected, source: a.source, retries: a.retries ?? s.retries };
    case "reset":
      return { ...initialState, source: s.source, connected: s.connected };
    case "snapshot": {
      const st = a.state || {};
      // Seed the chart series from the server's sliding history buffer so the
      // Brain charts render with real recent context the instant they mount.
      let series: MetricPoint[] = s.metricSeries;
      if (Array.isArray(st.history) && st.history.length) {
        // Pass through ALL numeric fields per point (valence/arousal/homeostasis
        // plus every extra metric) so any selected series can render from history.
        series = st.history
          .map((h: any) => {
            const pt: MetricPoint = { t: h.t } as MetricPoint;
            for (const k of Object.keys(h)) {
              if (k !== "cycle" && typeof h[k] === "number") (pt as any)[k] = h[k];
            }
            return pt;
          })
          .slice(-SERIES_CAP);
      } else if (Array.isArray(st.metric_series)) {
        series = st.metric_series.slice(-SERIES_CAP);
      }
      return {
        ...s,
        activeNode: st.active_node ?? null,
        nodeStatus: st.node_status ?? s.nodeStatus,
        narrative: st.narrative ?? s.narrative,
        affect: st.affect
          ? { valence: 0.5, arousal: 0.3, homeostasis: 0.8, extra: {}, ...st.affect }
          : s.affect,
        memory: Array.isArray(st.memory) ? st.memory.slice(-MEM_CAP) : s.memory,
        logs: Array.isArray(st.logs) ? st.logs.slice(-LOG_CAP) : s.logs,
        metrics: st.metrics ?? s.metrics,
        metricSeries: series,
        goals: Array.isArray(st.goals) ? st.goals : s.goals,
        cycle: st.cycle ?? s.cycle,
        activeFn: st.active_fn ?? s.activeFn,
        activeLane: st.active_lane ?? s.activeLane,
        fnRecent: Array.isArray(st.fn_recent) ? st.fn_recent : s.fnRecent,
        executive: st.executive ?? s.executive,
        monitor: st.monitor ?? s.monitor,
        workspace: st.workspace ?? s.workspace,
        interoception: st.interoception ?? s.interoception,
        llmCost: st.llm_cost ?? s.llmCost,
        extra: st.extra ?? s.extra,
        updatedAt: Date.now(),
      };
    }
    case "delta":
      return applyDelta(s, a.frame || {});
    default:
      return s;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────────────────────
// The live-stream transport (WebSocket today; the in-process bridge in B2) is
// resolved via getTransport(); this hook owns only the demo + reconnect policy.
const DEMO_FORCED = (import.meta.env.VITE_TELEMETRY_DEMO as string | undefined) === "1";

// ─────────────────────────────────────────────────────────────────────────────
// Hook
// ─────────────────────────────────────────────────────────────────────────────
export interface UseTelemetryOptions {
  /** Force the client-side synthetic generator instead of connecting to the backend. */
  demo?: boolean;
  /** Fall back to demo data if the socket can't connect after a few tries. */
  demoFallback?: boolean;
}

export function useTelemetry(opts: UseTelemetryOptions = {}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  // Close handle for the current telemetry subscription (the fn returned by
  // transport.connectTelemetry). Closing it is an *intentional* drop that won't
  // reconnect — used on unmount and (proactively) on user-initiated stop.
  const closeRef = useRef<null | (() => void)>(null);
  const retryRef = useRef(0);
  const demoTimer = useRef<number | null>(null);
  // Set when the user shuts Orrin down from the UI: the ensuing socket drop is
  // intentional, so show "Stopped" rather than "Reconnecting". Cleared on the
  // next successful connect so a restart auto-recovers to Live.
  const stoppedRef = useRef(false);

  const stopDemo = useCallback(() => {
    if (demoTimer.current != null) {
      window.clearInterval(demoTimer.current);
      demoTimer.current = null;
    }
  }, []);

  const startDemo = useCallback(() => {
    if (demoTimer.current != null) return;
    dispatch({ type: "status", connected: false, source: "demo" });
    const t0 = Date.now();
    let cycle = 0;
    const sources = ["affect", "select_function", "action_gate", "reward_engine", "homeostasis", "dream"];
    const levels: LogLevel[] = ["debug", "info", "info", "warn", "error"];
    demoTimer.current = window.setInterval(() => {
      cycle += 1;
      const node = LOOP_NODES[cycle % LOOP_NODES.length];
      const dt = (Date.now() - t0) / 1000;
      const valence = 0.5 + 0.35 * Math.sin(dt / 7);
      const arousal = 0.45 + 0.3 * Math.sin(dt / 3 + 1);
      const homeostasis = 0.7 + 0.25 * Math.sin(dt / 11);
      const narrative = {
        perceive: "Taking in the moment…",
        reflect: "Reflecting…",
        plan: "Planning next step…",
        act: "Acting on it…",
      }[node];
      const frame: any = {
        active_node: node,
        narrative,
        cycle,
        affect: {
          valence, arousal, homeostasis,
          extra: { motivation: 0.5 + 0.3 * Math.sin(dt / 5), threat_level: Math.max(0, 0.2 * Math.sin(dt / 4)) },
        },
        metrics: { valence, arousal, homeostasis },
        metric_point: { t: Date.now() / 1000, valence, arousal, homeostasis },
        logs: [{
          level: levels[Math.floor(Math.random() * levels.length)],
          source: sources[Math.floor(Math.random() * sources.length)],
          message: `cycle ${cycle}: ${node} stage processed (Δ=${Math.random().toFixed(3)})`,
          ts: Date.now() / 1000,
        }],
      };
      if (cycle % 2 === 0) {
        frame.memory = [{
          op: Math.random() > 0.5 ? "write" : "read",
          store: ["working", "long", "episodic", "semantic"][Math.floor(Math.random() * 4)],
          key: `node:${node}:${cycle}`,
          summary: ["goal progress snapshot", "reward trace updated", "affect setpoint compared", "association surfaced"][Math.floor(Math.random() * 4)],
          salience: Number(Math.random().toFixed(2)),
          ts: Date.now() / 1000,
        }];
      }
      dispatch({ type: "delta", frame });
    }, 900);
  }, []);

  const connect = useCallback(() => {
    if (opts.demo || DEMO_FORCED) {
      startDemo();
      return;
    }
    dispatch({ type: "status", connected: false, source: stoppedRef.current ? "stopped" : "connecting" });

    // The transport owns the socket (and the per-subscription intentional-close
    // flag that prevents a StrictMode remount from double-connecting). This hook
    // owns the demo + reconnect/backoff policy below.
    closeRef.current = getTransport().connectTelemetry({
      onOpen: () => {
        retryRef.current = 0;
        stoppedRef.current = false; // backend is back — leave the "stopped" state
        stopDemo();
        dispatch({ type: "status", connected: true, source: "live", retries: 0 });
      },
      onSnapshot: (st) => { checkFrame(st, "snapshot"); dispatch({ type: "snapshot", state: st }); },
      onDelta: (frame) => { checkFrame(frame, "delta"); dispatch({ type: "delta", frame }); },
      onClose: () => {
        // Don't react to a drop after we've unmounted.
        if (closeRef.current === null) return;
        retryRef.current += 1;
        // When the user stopped Orrin, show "Stopped" (intentional) rather than
        // "Reconnecting" (which reads like a fault). We KEEP retrying underneath so
        // the UI auto-recovers to Live if Orrin is restarted. Otherwise surface the
        // attempt count (L1) so a long outage reads "Reconnecting", not an
        // indefinite, indistinguishable "Connecting".
        dispatch(
          stoppedRef.current
            ? { type: "status", connected: false, source: "stopped" }
            : { type: "status", connected: false, source: "connecting", retries: retryRef.current },
        );
        if (opts.demoFallback && retryRef.current >= 3) {
          startDemo();
          return;
        }
        const delay = Math.min(1000 * 2 ** retryRef.current, 8000);
        window.setTimeout(() => closeRef.current !== null && connect(), delay);
      },
    });
  }, [opts.demo, opts.demoFallback, startDemo, stopDemo]);

  useEffect(() => {
    // The Stop button dispatches this after the backend acknowledges shutdown,
    // so the UI flips to "Stopped" immediately. We deliberately do NOT close the
    // stream here: the backend teardown drops it within a moment, which fires the
    // reconnect loop that (with stoppedRef set) shows "Stopped" while quietly
    // retrying — so the UI auto-recovers to "Live" if Orrin is restarted.
    const onStopped = () => {
      stoppedRef.current = true;
      dispatch({ type: "status", connected: false, source: "stopped" });
    };
    window.addEventListener("orrin:stopped", onStopped);
    connect();
    return () => {
      window.removeEventListener("orrin:stopped", onStopped);
      stopDemo();
      // Intentional close: the transport suppresses this subscription's onClose,
      // and nulling the ref stops any pending reconnect timer from firing.
      const close = closeRef.current;
      closeRef.current = null;
      close?.();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}

/**
 * One definition of "the live stream has gone stale" (UI_AUDIT M1). A socket can
 * stay `connected` while frames stop arriving (wedged backend / dead producer);
 * previously the Header and the Brain KPI each judged liveness differently, so
 * the Header could claim "Live" while the data was minutes old. Every consumer
 * now calls this. The internal tick keeps it honest with no frames arriving.
 */
export function useStreamStale(state: TelemetryState, thresholdMs = 15_000): boolean {
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 5_000);
    return () => clearInterval(id);
  }, []);
  return state.source === "live" && state.updatedAt > 0 && Date.now() - state.updatedAt > thresholdMs;
}
