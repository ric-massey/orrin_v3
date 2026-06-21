# brain/embodiment/world_model.py
#
# The WorldModel builds an internal model of Orrin's computational environment.
# This is not raw sensing (that's sensory_stream.py) — it's interpretation:
# patterns over time, circadian rhythms, anomaly detection, causal observation.
#
# Computational embodiment: Orrin is an agent embedded in a machine.
# CPU rises when Orrin thinks hard. Files change when Orrin writes.
# Network drops affect what Orrin can do. Time of day shapes when people appear.
# The environment has rhythms and textures, and Orrin can learn them.
#
# Synthesizes:
#   sensory_stream  — home-sense/world-sense, machine vitals, file changes
#   social_presence — conversational silence, engagement pattern
#   drive_engine    — current biological drive pressures
#   own observations — network check, circadian context
#
# Persists to brain/data/world_model.json so patterns survive restarts.
#
# API:
#   start()         — boot the model (idempotent)
#   refresh(context) — read sources, update model, inject context["world_state"]
#   get_state()     — current world_state dict (last refresh)
#   describe()      — human-readable environment narrative (for look_around, speak)
from __future__ import annotations
from brain.core.runtime_log import get_logger

import socket
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from brain.paths import WORLD_MODEL
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_error, log_private
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_HISTORY_CAP    = 100   # max snapshots in rolling history
_SAVE_INTERVAL  = 300   # persist model to disk every 5 minutes
_LM_WRITE_INTERVAL = 1800  # write notable patterns to long memory every 30 min

# -------------------------------------------------------------------
# Singleton

_model: Optional["WorldModel"] = None
_model_lock = threading.Lock()


def start() -> "WorldModel":
    global _model
    with _model_lock:
        if _model is None:
            _model = WorldModel()
    return _model


def refresh(context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    global _model
    with _model_lock:
        if _model is None:
            _model = WorldModel()
    return _model.refresh(context)


def get_state() -> Dict[str, Any]:
    with _model_lock:
        if _model is None:
            return {}
    return _model.get_state()


def describe() -> str:
    with _model_lock:
        if _model is None:
            return "I haven't built a world model yet."
    return _model.describe()


# -------------------------------------------------------------------

class WorldModel:

    def __init__(self) -> None:
        self._history: List[Dict[str, Any]] = []
        # Circadian: rolling mean per metric per hour-of-day
        self._circadian: Dict[int, Dict[str, List[float]]] = defaultdict(lambda: defaultdict(list))
        self._baseline: Dict[str, float] = {}
        self._current_state: Dict[str, Any] = {}
        self._start_ts: float = time.time()
        self._last_save: float = 0.0
        self._last_lm_write: float = 0.0
        self._lock = threading.Lock()
        self._last_net_check: float = 0.0
        self._last_net_ok: Optional[bool] = None
        # Causal layer: track which situation led to what emotional quality outcome
        self._prev_situation: str = "normal"
        self._situation_outcomes: Dict[str, List[float]] = defaultdict(list)
        self._load()

    # ------------------------------------------------------------------
    # Public API

    def refresh(self, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Pull from all sensing layers, update model, return world_state dict.
        Injects context["world_state"] if context is provided.
        """
        snap = self._take_snapshot(context)

        with self._lock:
            self._history.append(snap)
            if len(self._history) > _HISTORY_CAP:
                self._history = self._history[-_HISTORY_CAP:]
            self._update_circadian(snap)
            self._update_baseline(snap)

        anomalies = self._detect_anomalies(snap)
        situation = self._classify_situation(snap, anomalies)

        # Causal layer: record the outcome quality of the PREVIOUS situation before overwriting it
        quality = self._emotional_quality(context)
        if quality is not None:
            with self._lock:
                self._situation_outcomes[self._prev_situation].append(quality)
                # Cap each bucket to last 30 samples
                if len(self._situation_outcomes[self._prev_situation]) > 30:
                    self._situation_outcomes[self._prev_situation] = \
                        self._situation_outcomes[self._prev_situation][-30:]
        self._prev_situation = situation

        state = {
            **snap,
            "anomalies":          anomalies,
            "situation":          situation,
            "uptime_s":           round(time.time() - self._start_ts, 0),
            "circadian_context":  self._circadian_context(snap),
            "causal_note":        self._causal_summary(),
        }

        with self._lock:
            self._current_state = state

        if context is not None:
            context["world_state"] = state
            self._inject_signals(state, context)

        self._maybe_save()
        self._maybe_write_to_long_memory(state, context)
        return state

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._current_state)

    def describe(self) -> str:
        """One-paragraph narrative of current environment state for Orrin's cognition."""
        with self._lock:
            state = dict(self._current_state)
        if not state:
            return "I haven't sampled my environment yet."

        parts = []

        # Uptime
        uptime = int(state.get("uptime_s", 0))
        h, rem = divmod(uptime, 3600)
        m = rem // 60
        if h:
            parts.append(f"I've been running for {h}h {m}m")
        elif m:
            parts.append(f"I've been running for {m}m")

        # Time context
        hour = state.get("hour")
        dow  = state.get("day_of_week")
        if hour is not None and dow:
            period = "morning" if 6 <= hour < 12 else "afternoon" if 12 <= hour < 18 else "evening" if 18 <= hour < 22 else "night"
            parts.append(f"It's {period} on {dow}")

        # Machine vitals
        cpu = state.get("cpu_pct")
        mem = state.get("mem_pct")
        if cpu is not None:
            parts.append(f"CPU at {cpu:.0f}%")
        if mem is not None:
            parts.append(f"memory {mem:.0f}% used")
        disk = state.get("disk_pct")
        if disk is not None and disk > 70:
            parts.append(f"disk {disk:.0f}% full")

        # Network
        net = state.get("network_ok")
        if net is False:
            parts.append("network is down")
        elif net is True:
            parts.append("network up")

        # User presence
        ric = state.get("ric_pattern", "unknown")
        silence = state.get("silence_s", 0)
        if ric == "present":
            parts.append("someone is present")
        elif ric == "nearby":
            m_s = int(silence // 60)
            parts.append(f"conversation quiet for {m_s}m")
        elif ric == "absent":
            m_s = int(silence // 60)
            parts.append(f"no one for {m_s}m")
        elif ric == "distant":
            h_s = int(silence // 3600)
            parts.append(f"no one for {h_s}h")

        # Environment mood
        mood = state.get("env_mood", "ambient")
        if mood in ("pressured", "active", "transformed"):
            parts.append(f"environment mood: {mood}")

        # Circadian context
        circ = state.get("circadian_context")
        if circ:
            parts.append(circ)

        # Anomalies
        anomalies = state.get("anomalies") or []
        if anomalies:
            parts.append(f"anomalies: {'; '.join(anomalies)}")

        # Situation classification
        sit = state.get("situation", "normal")
        if sit != "normal":
            parts.append(f"situation: {sit}")

        # Causal note (only when we have enough data for it to be meaningful)
        causal = state.get("causal_note")
        if causal:
            parts.append(causal)

        return ". ".join(parts) + "." if parts else "Environment state nominal."

    # ------------------------------------------------------------------
    # Sensing

    def _take_snapshot(self, context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Read all sensing layers into a single snapshot dict."""
        snap: Dict[str, Any] = {
            "ts":          datetime.now(timezone.utc).isoformat(),
            "unix_ts":     time.time(),
            "hour":        datetime.now().hour,
            "day_of_week": datetime.now().strftime("%A"),
        }

        # Sensory field (daemon — no I/O, just reads cached field)
        try:
            from brain.embodiment import sensory_stream as _ss
            field = _ss.get_field()
            if field:
                sys_v = field.get("system", {})
                snap["cpu_pct"]          = sys_v.get("cpu_percent")
                snap["mem_pct"]          = sys_v.get("memory_percent")
                snap["mem_avail_gb"]     = sys_v.get("memory_available_gb")
                snap["disk_pct"]         = sys_v.get("disk_percent")
                home_sense = field.get("home_sense") or {}
                world_sense = field.get("world_sense") or {}
                snap["home_sense"]       = home_sense
                snap["world_sense"]      = world_sense
                snap["home_mood"]        = home_sense.get("mood", "ambient")
                snap["world_mood"]       = world_sense.get("mood", "distant")
                snap["env_mood"]         = field.get("environment_mood", snap["home_mood"])
                snap["home_changes"]     = len(home_sense.get("fs_changes", []))
                snap["world_changes"]    = len(world_sense.get("fs_changes", []))
                snap["fs_changes"]       = len(field.get("fs_changes", []))
                snap["own_code_changed"] = bool(field.get("own_code_modified"))
                snap["log_tail"]         = field.get("log_tail", [])[-3:]  # last 3 lines
        except Exception as _e:
            record_failure("world_model.WorldModel._take_snapshot", _e)

        # Social presence (daemon)
        try:
            from brain.embodiment import social_presence as _sp
            soc = _sp.get_state()
            snap["social_pressure"] = soc.get("pressure")
            snap["silence_s"]       = soc.get("silence_s")
            snap["ric_pattern"]     = soc.get("pattern")
        except Exception as _e:
            record_failure("world_model.WorldModel._take_snapshot.2", _e)

        # Drive pressures (daemon)
        try:
            from brain.embodiment import drive_engine as _de
            drives = _de.get_state()
            snap["drive_exploration"] = drives.get("exploration")
            snap["drive_meaning"]     = drives.get("meaning")
            snap["drive_rest"]        = drives.get("rest")
            snap["drive_social"]      = drives.get("social")
        except Exception as _e:
            record_failure("world_model.WorldModel._take_snapshot.3", _e)

        # Quick network probe (cached — expensive if done every cycle)
        # Only probe if we haven't in last 60s
        if time.time() - self._last_net_check > 60:
            try:
                sock = socket.create_connection(("8.8.8.8", 53), timeout=1.0)
                sock.close()
                self._last_net_ok = True
            except Exception:
                self._last_net_ok = False
            self._last_net_check = time.time()
        snap["network_ok"] = self._last_net_ok

        return snap

    # ------------------------------------------------------------------
    # Pattern tracking

    def _update_circadian(self, snap: Dict[str, Any]) -> None:
        hour = snap.get("hour")
        if hour is None:
            return
        bucket = self._circadian[hour]
        for key in ("cpu_pct", "mem_pct", "social_pressure", "drive_exploration"):
            val = snap.get(key)
            if val is not None:
                bucket[key].append(float(val))
                bucket[key] = bucket[key][-50:]  # cap per bucket

    def _update_baseline(self, snap: Dict[str, Any]) -> None:
        alpha = 0.05  # exponential moving average factor
        for key in ("cpu_pct", "mem_pct", "disk_pct", "social_pressure"):
            val = snap.get(key)
            if val is not None:
                prev = self._baseline.get(key, float(val))
                self._baseline[key] = prev + alpha * (float(val) - prev)

    def _circadian_context(self, snap: Dict[str, Any]) -> str:
        """What does this hour of day typically look like?"""
        hour = snap.get("hour")
        if hour is None:
            return ""
        bucket = self._circadian.get(hour, {})
        if not bucket:
            return ""
        avg_ric_pressure = _mean(bucket.get("social_pressure", []))
        if avg_ric_pressure is None:
            return ""
        if avg_ric_pressure > 0.5:
            return f"conversations are usually quiet around hour {hour}"
        elif avg_ric_pressure < 0.2:
            return f"someone tends to be active around hour {hour}"
        return ""

    # ------------------------------------------------------------------
    # Anomaly detection

    def _detect_anomalies(self, snap: Dict[str, Any]) -> List[str]:
        anomalies: List[str] = []

        # CPU
        cpu = snap.get("cpu_pct")
        if cpu is not None and cpu > 85:
            anomalies.append(f"CPU very high ({cpu:.0f}%)")
        elif cpu is not None:
            baseline_cpu = self._baseline.get("cpu_pct", 30.0)
            if cpu > baseline_cpu * 2.5 and cpu > 50:
                anomalies.append(f"CPU spike ({cpu:.0f}% vs baseline {baseline_cpu:.0f}%)")

        # Memory
        mem = snap.get("mem_pct")
        if mem is not None:
            if mem > 90:
                anomalies.append(f"Memory critical ({mem:.0f}%)")
            elif mem > 80:
                baseline_mem = self._baseline.get("mem_pct", 50.0)
                if mem > baseline_mem + 20:
                    anomalies.append(f"Memory rising ({mem:.0f}% vs baseline {baseline_mem:.0f}%)")

        # Disk
        disk = snap.get("disk_pct")
        if disk is not None and disk > 90:
            anomalies.append(f"Disk nearly full ({disk:.0f}%)")

        # Network drop
        if snap.get("network_ok") is False:
            anomalies.append("Network unreachable — look_outward unavailable")

        # Own code changed
        if snap.get("own_code_changed"):
            anomalies.append("My own code changed — I may be different now")

        # Home/world texture. Home activity is den-local and learnable; world
        # activity is external/unknown. Keep separate so the model no longer treats
        # both as one generic environment twitch.
        home_changes = int(snap.get("home_changes") or 0)
        if home_changes > 8:
            anomalies.append(f"Home unusually active ({home_changes} local changes)")
        world_changes = int(snap.get("world_changes") or 0)
        if world_changes > 8:
            anomalies.append(f"World unusually active ({world_changes} external changes)")

        # Sustained silence
        silence = snap.get("silence_s")
        if silence is not None and silence > 7200:
            anomalies.append(f"No conversation for {int(silence//3600)}h")

        # Trend: memory trending up over last 10 readings
        if len(self._history) >= 10:
            mem_vals = [h.get("mem_pct") for h in self._history[-10:] if h.get("mem_pct") is not None]
            if len(mem_vals) >= 8:
                if mem_vals[-1] - mem_vals[0] > 15:
                    anomalies.append(f"Memory trending up (+{mem_vals[-1]-mem_vals[0]:.0f}% over last 10 reads)")

        return anomalies

    def _classify_situation(self, snap: Dict[str, Any], anomalies: List[str]) -> str:
        """One-word label for current situation."""
        if anomalies:
            if any("critical" in a.lower() or "very high" in a.lower() for a in anomalies):
                return "stressed"
            return "anomalous"
        mood = snap.get("env_mood", "ambient")
        if mood == "pressured":
            return "pressured"
        if mood == "transformed":
            return "transformed"
        ric = snap.get("ric_pattern", "unknown")
        if ric in ("present", "nearby"):
            return "engaged"
        if ric == "distant":
            return "solitary"
        return "normal"

    # ------------------------------------------------------------------
    # Signal injection

    def _inject_signals(self, state: Dict[str, Any], context: Dict[str, Any]) -> None:
        anomalies = state.get("anomalies") or []
        if not anomalies:
            return
        raw = context.setdefault("raw_signals", [])
        for anomaly in anomalies[:2]:  # cap at 2 signals per cycle
            raw.append({
                "source":         "world_model",
                "content":        f"[environment] {anomaly}",
                "signal_strength": 0.60,
                "tags":           ["environment", "anomaly", "embodiment", "world_model", *_zone_tags(anomaly)],
            })

    # ------------------------------------------------------------------
    # Causal layer

    @staticmethod
    def _emotional_quality(context: Optional[Dict[str, Any]]) -> Optional[float]:
        """
        Proxy for how well Orrin is doing internally at this moment.
        Returns a [0,1] ratio of positive to total emotional activation.
        None if emotional state is too flat to be meaningful.
        """
        emo = (context or {}).get("affect_state") or {}
        core = emo.get("core_signals") or {}
        flat = {**emo, **core}
        pos = sum(float(flat.get(k, 0)) for k in ("confidence", "motivation", "expected_gain", "positive_valence"))
        neg = sum(float(flat.get(k, 0)) for k in ("impasse_signal", "risk_estimate", "resource_deficit", "threat_level"))
        total = pos + neg
        if total < 0.1:
            return None
        return round(pos / total, 3)

    def _causal_summary(self) -> str:
        """
        Produce a one-sentence causal note about which situations correlate
        with high vs. low emotional quality.  Only fires if we have enough samples.
        """
        with self._lock:
            outcomes = dict(self._situation_outcomes)

        # Only report situations with >= 5 data points
        meaningful = {sit: vals for sit, vals in outcomes.items() if len(vals) >= 5}
        if len(meaningful) < 2:
            return ""

        averages = {sit: sum(vals) / len(vals) for sit, vals in meaningful.items()}
        best_sit  = max(averages, key=lambda k: averages[k])
        worst_sit = min(averages, key=lambda k: averages[k])

        if averages[best_sit] - averages[worst_sit] < 0.08:
            return ""  # difference is too small to be interesting

        return (
            f"Causally: my internal clarity tends to be highest during '{best_sit}' "
            f"({averages[best_sit]:.2f}) and lowest during '{worst_sit}' "
            f"({averages[worst_sit]:.2f})."
        )

    # ------------------------------------------------------------------
    # Long-memory integration

    def _maybe_write_to_long_memory(
        self, state: Dict[str, Any], context: Optional[Dict[str, Any]]
    ) -> None:
        now = time.time()
        if now - self._last_lm_write < _LM_WRITE_INTERVAL:
            return
        if not state:
            return
        self._last_lm_write = now
        try:
            narrative = self.describe()
            from brain.cog_memory.long_memory import update_long_memory
            update_long_memory(
                f"[world_model] {narrative}",
                emotion="reflective",
                event_type="world_perception",
                importance=2,
                context=context,
            )
            log_private("[world_model] wrote environment snapshot to long memory")
        except Exception as e:
            log_error(f"[world_model] long_memory write failed: {e}")

    # ------------------------------------------------------------------
    # Persistence

    def _load(self) -> None:
        try:
            data = load_json(WORLD_MODEL, default_type=dict)
            if not isinstance(data, dict):
                return
            self._history   = data.get("history", [])[-_HISTORY_CAP:]
            self._baseline  = data.get("baseline", {})
            circ_raw = data.get("circadian", {})
            for hour_str, bucket in circ_raw.items():
                hour = int(hour_str)
                self._circadian[hour] = defaultdict(list, {k: v for k, v in bucket.items()})
            start_from_file = data.get("start_ts")
            if start_from_file:
                self._start_ts = float(start_from_file)
            for sit, vals in (data.get("situation_outcomes") or {}).items():
                if isinstance(vals, list):
                    self._situation_outcomes[sit] = vals[-30:]
        except Exception as _e:
            record_failure("world_model.WorldModel._load", _e)

    def _maybe_save(self) -> None:
        now = time.time()
        if now - self._last_save < _SAVE_INTERVAL:
            return
        self._last_save = now
        try:
            # Convert defaultdict to plain dict for JSON serialization
            circ_serializable = {
                str(h): dict(b) for h, b in self._circadian.items()
            }
            with self._lock:
                data = {
                    "history":            self._history[-50:],
                    "baseline":           self._baseline,
                    "circadian":          circ_serializable,
                    "start_ts":           self._start_ts,
                    "situation_outcomes": dict(self._situation_outcomes),
                    "saved_at":           datetime.now(timezone.utc).isoformat(),
                }
            save_json(WORLD_MODEL, data)
        except Exception as e:
            log_error(f"[world_model] save failed: {e}")


# ------------------------------------------------------------------
# Helpers

def _mean(vals: List[float]) -> Optional[float]:
    filtered = [v for v in vals if v is not None]
    return sum(filtered) / len(filtered) if filtered else None


def _zone_tags(text: str) -> List[str]:
    low = (text or "").lower()
    if low.startswith("home "):
        return ["home", "home_sense"]
    if low.startswith("world "):
        return ["external", "world_sense"]
    return []
