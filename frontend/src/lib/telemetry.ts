import { useCallback, useEffect, useReducer, useRef } from "react";
import { LogLevel, LOOP_NODES, MetricPoint, TelemetryState } from "./types";

// Re-export the data contracts so existing `@/lib/telemetry` imports keep working.
export * from "./types";

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
  extra: {},
  connected: false,
  source: "connecting",
  updatedAt: 0,
};

// ─────────────────────────────────────────────────────────────────────────────
// Reducer
// ─────────────────────────────────────────────────────────────────────────────
type Action =
  | { type: "snapshot"; state: any }
  | { type: "delta"; frame: any }
  | { type: "status"; connected: boolean; source: TelemetryState["source"] }
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
  if (f.extra != null) next.extra = { ...s.extra, ...f.extra };
  next.updatedAt = Date.now();
  return next;
}

function reducer(s: TelemetryState, a: Action): TelemetryState {
  switch (a.type) {
    case "status":
      return { ...s, connected: a.connected, source: a.source };
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
function wsUrl(): string {
  const explicit = import.meta.env.VITE_TELEMETRY_WS as string | undefined;
  if (explicit) return explicit;
  const envHost = import.meta.env.VITE_TELEMETRY_HOST as string | undefined;
  // When accessed remotely (tunnel/LAN), proxy /ws through Vite so the
  // WebSocket uses the same host/port as the page instead of hardcoded localhost.
  if (!envHost) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${proto}//${window.location.host}/ws/telemetry`;
  }
  return `ws://${envHost}/ws/telemetry`;
}

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
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef(0);
  const demoTimer = useRef<number | null>(null);
  const closedRef = useRef(false);

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
    let ws: WebSocket;
    try {
      ws = new WebSocket(wsUrl());
    } catch {
      if (opts.demoFallback) startDemo();
      return;
    }
    wsRef.current = ws;
    dispatch({ type: "status", connected: false, source: "connecting" });

    ws.onopen = () => {
      retryRef.current = 0;
      stopDemo();
      dispatch({ type: "status", connected: true, source: "live" });
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "snapshot") dispatch({ type: "snapshot", state: msg.state });
        else if (msg.type === "delta") dispatch({ type: "delta", frame: msg.frame });
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = () => {
      dispatch({ type: "status", connected: false, source: "connecting" });
      // Don't reconnect a socket we deliberately closed. closedRef alone is racy:
      // under React StrictMode the cleanup runs, then the remount resets
      // closedRef=false BEFORE this (async) onclose fires — so the dead socket
      // would reconnect, leaving TWO live sockets and every message logged twice.
      // The per-socket flag survives the remount and prevents that.
      if (closedRef.current || (ws as unknown as { _intentional?: boolean })._intentional) return;
      retryRef.current += 1;
      if (opts.demoFallback && retryRef.current >= 3) {
        startDemo();
        return;
      }
      const delay = Math.min(1000 * 2 ** retryRef.current, 8000);
      window.setTimeout(() => !closedRef.current && connect(), delay);
    };
    ws.onerror = () => ws.close();
  }, [opts.demo, opts.demoFallback, startDemo, stopDemo]);

  useEffect(() => {
    closedRef.current = false;
    connect();
    return () => {
      closedRef.current = true;
      stopDemo();
      const sock = wsRef.current;
      if (sock) (sock as unknown as { _intentional?: boolean })._intentional = true;
      sock?.close();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return state;
}
