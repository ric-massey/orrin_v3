"""
backend/server/hub.py — the telemetry Hub.

Owns the connected-client registry and the single rolling "latest state". Producers
send partial frames (just an affect tick, just a log line); `merge()` folds each
into the state and returns the normalized delta to broadcast. New clients are
hydrated with a full snapshot (including the replay history) on connect.
"""
from __future__ import annotations

import asyncio
import collections
import time
from typing import Any, Callable, Deque, Dict, List, Set

import json
from pathlib import Path

from fastapi import WebSocket

import logging

from .config import HISTORY_CAP, INPUT_CAP, LOG_CAP, LOOP_NODES, MEMORY_CAP, METRIC_CAP
from .schema import LATEST_WINS_KEYS, validate_frame

_log = logging.getLogger(__name__)

# Persist the metric history across restarts so the System Metrics chart is
# CONTINUOUS — it doesn't blank out every time the brain/telemetry process bounces.
_HISTORY_FILE = Path(__file__).resolve().parents[2] / "brain" / "data" / "telemetry_history.json"
# Append-only long-term archive of every telemetry point. _HISTORY_FILE is a
# rolling HISTORY_CAP window (sized for the live UI chart); it overwrites old
# points, so it can never answer "how did valence/arousal/homeostasis/curiosity
# change over a whole life?". This JSONL archive keeps every point forever (one
# line per point) so metric history survives past the 240-sample window and
# across restarts. Best-effort: telemetry must never crash the loop.
_ARCHIVE_FILE = Path(__file__).resolve().parents[2] / "brain" / "data" / "telemetry_archive.jsonl"


def _load_history() -> List[Dict[str, Any]]:
    try:
        d = json.loads(_HISTORY_FILE.read_text("utf-8"))
        return d if isinstance(d, list) else []
    except Exception:
        return []


def _save_history(points: List[Dict[str, Any]]) -> None:
    try:
        _HISTORY_FILE.write_text(json.dumps(points[-HISTORY_CAP:]), encoding="utf-8")
    except Exception:
        pass


def _archive_points(points: List[Dict[str, Any]]) -> None:
    """Append telemetry points to the uncapped JSONL archive, one line each."""
    if not points:
        return
    try:
        with _ARCHIVE_FILE.open("a", encoding="utf-8") as fh:
            for p in points:
                fh.write(json.dumps(p) + "\n")
    except Exception:
        pass


def clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _to_float(v: Any):
    """Coerce to float, or None if it isn't numeric. Used so a single non-numeric
    metric value can't raise inside merge() and drop the whole frame (logs/memory
    included) — UI_AUDIT L3."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f == f else None  # drop NaN (NaN != NaN)


def stamp(record: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure a record carries a timestamp (epoch seconds)."""
    if not record.get("ts"):
        record = {**record, "ts": time.time()}
    return record


class Hub:
    """Connection registry + merged latest state + replay/input buffers."""

    def __init__(self) -> None:
        self._clients: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self.state: Dict[str, Any] = {
            "active_node": None,
            "node_status": {n: "idle" for n in LOOP_NODES},
            "narrative": "Idle",
            "affect": {"valence": 0.5, "arousal": 0.3, "homeostasis": 0.8, "extra": {}},
            "memory": [],          # rolling list of MemoryRecord dicts
            "logs": [],            # rolling list of LogLine dicts
            "metrics": {},         # latest scalar values
            "metric_series": [],   # rolling [{t, <metric>: v, ...}] for charts
            "goals": [],           # latest goal set (committed + list) from the loop
            "cycle": 0,
            "active_fn": None,     # the cognitive function running right now
            "active_lane": None,   # deliberate | executive (Gap 3)
            "fn_recent": [],       # recent [{fn, cycle, lane, reward}] for the live "active light"
            "catalog": None,       # function map {functions, subsystems} (pushed once)
            "executive": None,     # §19.1 Executive lane summary
            "monitor": None,       # Monitor breakthroughs + watchdog board
            "workspace": None,     # Global Workspace winner (+candidates)
            "interoception": None, # live per-act cost model (Fix 7)
            "llm_cost": None,      # reasoning-cache health + symbolic-vs-LLM ratio
            "updated_at": time.time(),
        }
        # Sliding affect/metric history replayed to new clients so the Brain
        # charts are populated immediately on connect / tab switch. Seeded from the
        # persisted file so the chart continues across restarts instead of resetting.
        self.history: Deque[Dict[str, Any]] = collections.deque(_load_history(), maxlen=HISTORY_CAP)
        if self.history:
            self.state["metric_series"] = list(self.history)[-METRIC_CAP:]
        self._hist_writes = 0
        self._contract_warnings = 0  # capped count of wire-contract violations (Phase 5.2)
        self._archive_buf: List[Dict[str, Any]] = []  # points pending archive flush
        # User inputs from the Face awaiting the core loop, and agent replies
        # awaiting Face pickup (the closed integration loop).
        self.inputs: Deque[Dict[str, Any]] = collections.deque(maxlen=INPUT_CAP)
        self.responses: "collections.OrderedDict[str, Dict[str, Any]]" = collections.OrderedDict()
        # In-process subscribers (the pywebview bridge). Every broadcast is also
        # fanned out to these synchronously, so the native window receives the
        # exact same snapshot/delta stream as a WebSocket client — with no socket.
        self._sinks: List[Callable[[Dict[str, Any]], None]] = []

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ── in-process sinks (the pywebview bridge) ──────────────────────────────
    def add_sink(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        if fn not in self._sinks:
            self._sinks.append(fn)

    def remove_sink(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        with __import__("contextlib").suppress(ValueError):
            self._sinks.remove(fn)

    def publish_sync(self, payload: Dict[str, Any]) -> None:
        """Fan a snapshot/delta out to in-process subscribers. Never raises."""
        for fn in list(self._sinks):
            try:
                fn(payload)
            except Exception:
                pass

    # ── connection lifecycle ─────────────────────────────────────────────────
    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.add(ws)
        snapshot = {**self.state, "history": list(self.history)}
        await self._safe_send(ws, {"type": "snapshot", "state": snapshot})

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def _safe_send(self, ws: WebSocket, payload: Dict[str, Any]) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        async with self._lock:
            targets = list(self._clients)
        dead: List[WebSocket] = []
        for ws in targets:
            if not await self._safe_send(ws, payload):
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._clients.discard(ws)
        # Same stream to the in-process bridge (native window) — so a delta merged
        # by an endpoint (e.g. agent/input, shutdown) reaches it too, not only the
        # producer's frames.
        self.publish_sync(payload)

    # ── state merge ──────────────────────────────────────────────────────────
    def merge(self, frame: Dict[str, Any]) -> Dict[str, Any]:
        """Fold a partial frame into the latest state; return the delta to broadcast."""
        # Producer-side boundary validation (Phase 5.2): check the frame against the
        # wire contract (schema.TelemetryFrame) before it enters the rolling state.
        # Non-fatal — telemetry must never crash the loop — so a contract violation
        # is logged loudly (capped) and the frame is still merged. This catches a
        # genuine type error (a string where a float belongs) at the producer, the
        # symmetric half of the frontend's zod check at the consumer.
        errs = validate_frame(frame)
        if errs:
            self._contract_warnings += 1
            if self._contract_warnings <= 25:
                _log.warning("telemetry frame violates the wire contract: %s", "; ".join(errs[:5]))

        s = self.state
        delta: Dict[str, Any] = {}

        # Scalars / latest-wins blobs (overwrite when present). The key list is
        # data-driven from schema.LATEST_WINS_KEYS (Fix 7) so a producer key can
        # never again be emitted and silently dropped here — the contract test
        # asserts producer keywords ⊆ that tuple.
        for key in LATEST_WINS_KEYS:
            if frame.get(key) is not None:
                s[key] = frame[key]
                delta[key] = frame[key]

        # Goals — latest-wins list of the loop's current goal set.
        if isinstance(frame.get("goals"), list):
            s["goals"] = frame["goals"]
            delta["goals"] = frame["goals"]

        # Active node + per-node status
        active = frame.get("active_node")
        node_status = frame.get("node_status") or {}
        if active is not None:
            s["active_node"] = active
            if not node_status:  # derive: active = "active", the rest idle
                node_status = {n: ("active" if n == active else "idle") for n in LOOP_NODES}
            delta["active_node"] = active
        if node_status:
            s["node_status"] = {**s.get("node_status", {}), **node_status}
            delta["node_status"] = s["node_status"]

        # Affect (merge non-null fields)
        af = frame.get("affect")
        if isinstance(af, dict):
            cur = dict(s.get("affect") or {})
            for k in ("valence", "arousal", "homeostasis"):
                if af.get(k) is not None:
                    cur[k] = clamp01(af[k])
            if isinstance(af.get("extra"), dict):
                cur["extra"] = {**cur.get("extra", {}), **{k: clamp01(v) for k, v in af["extra"].items()}}
            s["affect"] = cur
            delta["affect"] = cur

        # Metrics (scalar dict + rolling series for charts). Coerce defensively:
        # a non-numeric/NaN value is dropped rather than allowed to raise and lose
        # the whole frame's logs/memory (L3).
        metrics = frame.get("metrics")
        if isinstance(metrics, dict) and metrics:
            clean = {k: f for k, v in metrics.items() if (f := _to_float(v)) is not None}
            if clean:
                s["metrics"] = {**s.get("metrics", {}), **clean}
                point = {"t": round(time.time(), 3), **clean}
                s["metric_series"] = (s.get("metric_series", []) + [point])[-METRIC_CAP:]
                delta["metrics"] = s["metrics"]
                delta["metric_point"] = point

        # Memory records (append to ring; broadcast only the new ones)
        mem = frame.get("memory") or []
        if mem:
            new = [stamp(m) for m in mem if isinstance(m, dict)]
            s["memory"] = (s.get("memory", []) + new)[-MEMORY_CAP:]
            delta["memory"] = new

        # Logs (append to ring; broadcast only the new ones)
        logs = frame.get("logs") or []
        if logs:
            new = [stamp(l) for l in logs if isinstance(l, dict)]
            s["logs"] = (s.get("logs", []) + new)[-LOG_CAP:]
            delta["logs"] = new

        if isinstance(frame.get("extra"), dict) and frame["extra"]:
            s["extra"] = {**s.get("extra", {}), **frame["extra"]}
            delta["extra"] = frame["extra"]

        # Record a history point whenever affect or metrics moved. Store ALL latest
        # metric values (valence/arousal/homeostasis + every extra) so reconnecting
        # clients can chart any selected metric with real recent history.
        if "affect" in delta or "metrics" in delta:
            a = s.get("affect", {})
            point: Dict[str, Any] = {
                "t": round(time.time(), 3),
                "cycle": s.get("cycle", 0),
                "valence": a.get("valence"),
                "arousal": a.get("arousal"),
                "homeostasis": a.get("homeostasis"),
            }
            for k, v in (s.get("metrics") or {}).items():
                if isinstance(v, (int, float)):
                    point[k] = float(v)
            self.history.append(point)
            self._archive_buf.append(point)
            # Flush to disk every ~15 points so the chart survives restarts without
            # hammering the filesystem each cycle. Same cadence flushes the buffered
            # points to the uncapped archive, so long-term metric history is retained
            # beyond the rolling HISTORY_CAP window.
            self._hist_writes += 1
            if self._hist_writes % 15 == 0:
                _save_history(list(self.history))
                _archive_points(self._archive_buf)
                self._archive_buf = []

        s["updated_at"] = time.time()
        return delta
