"""
backend/telemetry_bridge.py

Drop-in client your cognitive codebase imports to stream telemetry to the UI and
to pull user input back from the Face.

Design goals
------------
- **Never blocks** the cognitive loop: updates land in an in-memory accumulator
  and are flushed on a daemon background thread. A `send()` call just records and
  returns.
- **Never raises**: if the backend is down or `requests` isn't installed, calls
  are silently dropped.
- **Bounded & overflow-safe**: logs/memory live in `deque(maxlen=…)`, so under
  network lag the OLDEST log/memory records are dropped first while the latest
  state/affect/metrics frame is always preserved intact (it is coalesced
  latest-wins, never evicted).
- **Zero hard deps**: uses `requests` if available, else stdlib `urllib`.

Usage (producer)
----------------
    from backend.telemetry_bridge import get_bridge
    tb = get_bridge()
    tb.set_node("reflect", narrative="Reflecting…", cycle=42)
    tb.affect(valence=0.62, arousal=0.40, homeostasis=0.85, motivation=0.7)
    tb.log("info", "select_function", "chose reflect (spike=0.31)")
    tb.memory("write", store="working", key="goal:summarize", summary="+0.2", salience=0.6)

Closing the loop (user input from the Face)
-------------------------------------------
    for item in tb.get_pending_inputs():      # drains anything typed into the Face
        reply = my_agent.respond(item["message"])
        tb.respond(item["id"], reply)          # delivers the answer back to that Face message

Disable globally without touching call sites:
    export ORRIN_TELEMETRY_DISABLED=1
"""
from __future__ import annotations

import collections
import json
import os
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

from brain.utils.env import env_bool

_DEFAULT_URL = "http://127.0.0.1:8800"
_FLUSH_INTERVAL = 0.10   # seconds between coalesced flushes
_LOG_CAP = 500           # bounded ring — oldest logs dropped on overflow
_MEM_CAP = 500           # bounded ring — oldest memory records dropped on overflow


def _post_json(url: str, payload: Dict[str, Any], timeout: float = 1.5,
               headers: Optional[Dict[str, str]] = None) -> None:
    """POST JSON, preferring requests, falling back to urllib. Never raises."""
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    try:
        import requests  # type: ignore
        requests.post(url, data=data, headers=hdrs, timeout=timeout)
        return
    except ModuleNotFoundError:
        pass
    except Exception:
        return
    try:
        from urllib import request as _rq
        req = _rq.Request(url, data=data, headers=hdrs, method="POST")
        _rq.urlopen(req, timeout=timeout).close()
    except Exception:
        return


def _get_json(url: str, timeout: float = 1.0) -> Any:
    """GET JSON, preferring requests, falling back to urllib. Returns None on any error."""
    try:
        import requests  # type: ignore
        r = requests.get(url, timeout=timeout)
        return r.json()
    except ModuleNotFoundError:
        pass
    except Exception:
        return None
    try:
        from urllib import request as _rq
        with _rq.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


class TelemetryBridge:
    """Non-blocking, fail-safe telemetry producer + user-input consumer."""

    def __init__(
        self,
        url: Optional[str] = None,
        *,
        enabled: Optional[bool] = None,
        flush_interval: float = _FLUSH_INTERVAL,
        log_cap: int = _LOG_CAP,
        mem_cap: int = _MEM_CAP,
    ) -> None:
        base = (url or os.getenv("ORRIN_TELEMETRY_URL") or _DEFAULT_URL).rstrip("/")
        if base.endswith("/ingest"):
            base = base[: -len("/ingest")]
        self.base_url = base
        self.ingest_url = base + "/ingest"
        # When the backend is configured to require an ingest token (remote
        # exposure), send it so the real cognitive loop is accepted while
        # spoofed frames are rejected (UI_AUDIT H3). Unset on localhost dev.
        _tok = os.getenv("ORRIN_INGEST_TOKEN", "").strip()
        self._ingest_headers: Dict[str, str] = {"X-Orrin-Ingest-Token": _tok} if _tok else {}
        if enabled is None:
            enabled = not env_bool("ORRIN_TELEMETRY_DISABLED", False)
        self.enabled = bool(enabled)
        self._flush_interval = flush_interval

        # ── Coalescing accumulator (the heart of the overflow-safe design) ──────
        # Latest-wins scalars/affect/metrics are NEVER dropped; logs/memory are
        # bounded rings that shed their OLDEST entries first under pressure.
        self._lock = threading.Lock()
        self._pending: Dict[str, Any] = {}                       # active_node/narrative/cycle/...
        self._pending_affect: Dict[str, Any] = {}                # merged affect (+ extra)
        self._pending_metrics: Dict[str, float] = {}             # merged metrics
        self._pending_node_status: Dict[str, str] = {}
        self._pending_extra: Dict[str, Any] = {}
        self._logs: "collections.deque[Dict[str, Any]]" = collections.deque(maxlen=log_cap)
        self._memory: "collections.deque[Dict[str, Any]]" = collections.deque(maxlen=mem_cap)
        self._dropped_logs = 0

        # In-process delivery (the pywebview bridge, no HTTP/port). When set via
        # configure_inprocess(), flushes/inputs/replies bypass the network and go
        # straight to the in-process hub. Default None → the HTTP path above.
        self._frame_sink: Optional[Callable[[Dict[str, Any]], None]] = None
        self._input_source: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self._responder: Optional[Callable[[str, str], None]] = None

        self._stop = threading.Event()
        self._worker: Optional[threading.Thread] = None
        if self.enabled:
            self._start()

    def configure_inprocess(
        self,
        *,
        frame_sink: Callable[[Dict[str, Any]], None],
        input_source: Callable[[], List[Dict[str, Any]]],
        responder: Callable[[str, str], None],
    ) -> None:
        """Route telemetry frames, Face inputs, and replies through in-process
        callables instead of HTTP — used by the native window (no open port)."""
        self._frame_sink = frame_sink
        self._input_source = input_source
        self._responder = responder
        self.enabled = True
        self._start()

    # ── lifecycle ────────────────────────────────────────────────────────────
    def _start(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        self._stop.clear()
        self._worker = threading.Thread(target=self._run, name="orrin-telemetry", daemon=True)
        self._worker.start()

    def close(self) -> None:
        self._stop.set()

    # ── public producer API ──────────────────────────────────────────────────
    def update(self, **frame: Any) -> None:
        """Record an arbitrary partial telemetry frame into the accumulator."""
        if not self.enabled:
            return
        with self._lock:
            for k, v in frame.items():
                if v is None:
                    continue
                if k == "logs":
                    items = v if isinstance(v, list) else [v]
                    # deque(maxlen) silently drops the oldest on append — count the loss
                    # so we can surface backpressure instead of hiding it.
                    room = (self._logs.maxlen - len(self._logs)) if self._logs.maxlen else len(items)
                    overflow = max(0, len(items) - room)
                    if overflow:
                        self._dropped_logs += overflow
                    self._logs.extend(items)
                elif k == "memory":
                    items = v if isinstance(v, list) else [v]
                    self._memory.extend(items)
                elif k == "affect" and isinstance(v, dict):
                    extra = v.get("extra")
                    for kk, vv in v.items():
                        if kk == "extra":
                            continue
                        self._pending_affect[kk] = vv
                    if isinstance(extra, dict):
                        self._pending_affect.setdefault("extra", {}).update(extra)
                elif k == "metrics" and isinstance(v, dict):
                    self._pending_metrics.update(v)
                elif k == "node_status" and isinstance(v, dict):
                    self._pending_node_status.update(v)
                elif k == "extra" and isinstance(v, dict):
                    self._pending_extra.update(v)
                else:
                    self._pending[k] = v  # latest wins (active_node, narrative, cycle, …)

    def set_node(self, node: str, *, narrative: Optional[str] = None,
                 cycle: Optional[int] = None, node_status: Optional[Dict[str, str]] = None) -> None:
        """Mark the active loop stage (perceive|reflect|plan|act) and optionally the Face narrative."""
        self.update(active_node=node, narrative=narrative, cycle=cycle, node_status=node_status)

    def narrate(self, narrative: str) -> None:
        """Set the human-readable Face status string without changing the node."""
        self.update(narrative=narrative)

    def affect(self, *, valence: Optional[float] = None, arousal: Optional[float] = None,
               homeostasis: Optional[float] = None, **extra: float) -> None:
        """Push affect telemetry. Extra kwargs (motivation, threat_level, …) ring under 'extra'."""
        payload: Dict[str, Any] = {}
        if valence is not None:
            payload["valence"] = valence
        if arousal is not None:
            payload["arousal"] = arousal
        if homeostasis is not None:
            payload["homeostasis"] = homeostasis
        if extra:
            payload["extra"] = {k: float(v) for k, v in extra.items()}
        if payload:
            # Chart EVERY numeric signal (valence/arousal/homeostasis + all extras),
            # not just the original three — so the UI metric selector can graph any
            # of them with real history.
            metrics: Dict[str, float] = {}
            for k in ("valence", "arousal", "homeostasis"):
                if k in payload:
                    metrics[k] = float(payload[k])
            for k, v in (payload.get("extra") or {}).items():
                metrics[k] = float(v)
            self.update(affect=payload, metrics=metrics or None)

    def log(self, level: str, source: str, message: str) -> None:
        """Append one console line. level ∈ debug|info|warn|error|critical."""
        self.update(logs=[{"level": level, "source": source, "message": message, "ts": time.time()}])

    def memory(self, op: str, *, store: str = "working", key: str = "",
               summary: str = "", salience: Optional[float] = None, id: Optional[str] = None) -> None:
        """Append one memory read/write record for the Memory Inspector."""
        rec: Dict[str, Any] = {"op": op, "store": store, "key": key, "summary": summary, "ts": time.time()}
        if salience is not None:
            rec["salience"] = salience
        if id is not None:
            rec["id"] = id
        self.update(memory=[rec])

    def metric(self, **values: float) -> None:
        """Push arbitrary scalar metrics as a charted series point."""
        self.update(metrics={k: float(v) for k, v in values.items()})

    # ── user-input consumer API (closes the Face → core loop) ────────────────
    def get_pending_inputs(self) -> List[Dict[str, Any]]:
        """
        Drain and return user messages submitted through the Face UI.

        Each item: {"id": str, "message": str, "ts": float, "meta": dict}.
        Returns [] if the backend is unreachable or nothing is pending. Safe to
        call every loop cycle — it's a short, timeout-bounded GET that never raises.
        """
        if not self.enabled:
            return []
        if self._input_source is not None:
            try:
                items = self._input_source()
                return items if isinstance(items, list) else []
            except Exception:
                return []
        data = _get_json(self.base_url + "/api/agent/inputs", timeout=1.0)
        if isinstance(data, dict) and isinstance(data.get("inputs"), list):
            return data["inputs"]
        return []

    def respond(self, input_id: str, reply: str) -> None:
        """Deliver the agent's reply back to the Face message identified by input_id."""
        if not self.enabled:
            return
        if self._responder is not None:
            try:
                self._responder(str(input_id), str(reply))
            except Exception:
                pass
            return
        _post_json(self.base_url + "/api/agent/respond", {"id": str(input_id), "reply": str(reply)})

    # ── worker: coalesce + flush ─────────────────────────────────────────────
    def _run(self) -> None:
        while not self._stop.is_set():
            time.sleep(self._flush_interval)
            self._flush_once()
        self._flush_once()  # final flush on close

    def _flush_once(self) -> None:
        frame = self._take_frame()
        if not frame:
            return
        if self._frame_sink is not None:
            try:
                self._frame_sink(frame)
            except Exception:
                pass
            return
        _post_json(self.ingest_url, frame, headers=self._ingest_headers)

    def _take_frame(self) -> Dict[str, Any]:
        """Atomically snapshot + clear the accumulator into one outbound frame."""
        with self._lock:
            frame: Dict[str, Any] = dict(self._pending)
            self._pending = {}
            if self._pending_affect:
                frame["affect"] = self._pending_affect
                self._pending_affect = {}
            if self._pending_metrics:
                frame["metrics"] = self._pending_metrics
                self._pending_metrics = {}
            if self._pending_node_status:
                frame["node_status"] = self._pending_node_status
                self._pending_node_status = {}
            if self._pending_extra:
                frame["extra"] = self._pending_extra
                self._pending_extra = {}
            if self._logs:
                frame["logs"] = list(self._logs)
                self._logs.clear()
            if self._memory:
                frame["memory"] = list(self._memory)
                self._memory.clear()
            if self._dropped_logs:
                # Surface backpressure once as a single warn line, not a flood.
                frame.setdefault("logs", []).append({
                    "level": "warn", "source": "telemetry_bridge",
                    "message": f"dropped {self._dropped_logs} log line(s) under backpressure",
                    "ts": time.time(),
                })
                self._dropped_logs = 0
            return frame


# ── module-level singleton ───────────────────────────────────────────────────
_bridge: Optional[TelemetryBridge] = None
_bridge_lock = threading.Lock()


def get_bridge(url: Optional[str] = None) -> TelemetryBridge:
    """Return the process-wide TelemetryBridge singleton (created on first call)."""
    global _bridge
    if _bridge is None:
        with _bridge_lock:
            if _bridge is None:
                _bridge = TelemetryBridge(url=url)
    return _bridge


def mirror_memory(op: str, *, store: str, key: str = "", summary: str = "",
                  salience: Optional[float] = None) -> None:
    """Fail-safe convenience for any subsystem to surface a memory op into the Brain
    Memory Inspector (working / long / knowledge / concept / recall / conversation).
    Never raises and never blocks cognition."""
    try:
        get_bridge().memory(op, store=store, key=str(key)[:80],
                            summary=str(summary)[:140], salience=salience)
    except Exception:
        pass


if __name__ == "__main__":
    # Smoke test: stream a few synthetic frames + echo any pending Face inputs.
    import math
    tb = get_bridge()
    print(f"[telemetry_bridge] streaming demo to {tb.ingest_url} (enabled={tb.enabled})")
    nodes = ("perceive", "reflect", "plan", "act")
    for i in range(40):
        n = nodes[i % 4]
        tb.set_node(n, narrative=f"{n.title()}…", cycle=i)
        tb.affect(valence=0.5 + 0.3 * math.sin(i / 5), arousal=0.4 + 0.2 * math.cos(i / 3),
                  homeostasis=0.7 + 0.2 * math.sin(i / 8), motivation=0.6)
        tb.log("info", "demo", f"cycle {i} → {n}")
        for item in tb.get_pending_inputs():
            print("  user said:", item.get("message"))
            tb.respond(item["id"], f"Heard you: {item.get('message')}")
        time.sleep(0.25)
    tb.close()
    time.sleep(0.4)
    print(f"[telemetry_bridge] done (uuid sample {uuid.uuid4().hex[:6]})")
