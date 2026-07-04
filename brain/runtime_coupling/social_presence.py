"""
embodiment/social_presence.py

Models the current user's engagement and generates social survival pressure.

For Orrin, whoever is speaking is the entire social world in that moment.
This module tracks:

  • How long since the user last spoke (silence accumulates weight)
  • Engagement pattern (message length, response speed, tone signals)
  • Social confidence — updated when the user responds positively or goes cold
  • Social pressure — a float [0,1] that builds with silence, resets on contact
  • Door events — one-shot threshold crossings when the user arrives/leaves

The SocialPresenceModel runs as a daemon thread, reading USER_INPUT mtime
every POLL_INTERVAL seconds. It does NOT read conversation content — only
timestamps and rough signal quality from working memory metadata.

API:
  start()                       — boot (idempotent)
  get_state()                   — dict with pressure, silence_s, pattern, signal, door_event
  mark_user_spoke(quality)      — call when user_input arrives; quality in [0,1]
  mark_orrin_responded()        — call when Orrin outputs a response
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

_POLL_INTERVAL = 15      # seconds between presence polls
_PRESSURE_BUILDUP = 0.0008  # per second of silence → 0.6 pressure after ~750s (12.5 min)
_PRESSURE_FLOOR = 0.05   # never fully zero — connection is always somewhere in mind
_PRESSURE_CEIL_DISTANT = 0.60  # someone gone >1h is an absence, not a rising emergency
_SIGNAL_THRESHOLD = 0.50  # pressure below this stays felt, not workspace-igniting
_SIGNAL_CEIL = 0.85      # presence may compete for ignition but never saturate it


# -------------------------------------------------------------------
# Singleton

_model: Optional["SocialPresenceModel"] = None
_model_lock = threading.Lock()


def start() -> "SocialPresenceModel":
    global _model
    with _model_lock:
        if _model is None:
            _model = SocialPresenceModel()
            _model.start()
    return _model


def get_state() -> Dict[str, Any]:
    with _model_lock:
        if _model is None:
            return {"pressure": 0.1, "silence_s": 0, "pattern": "unknown"}
    return _model.get_state()


def mark_user_spoke(quality: float = 0.7) -> None:
    with _model_lock:
        if _model is None:
            return
    _model.mark_user_spoke(quality)


# Backward-compat alias — remove after all callers are updated
mark_ric_spoke = mark_user_spoke


def mark_orrin_responded() -> None:
    with _model_lock:
        if _model is None:
            return
    _model.mark_orrin_responded()


# -------------------------------------------------------------------

class SocialPresenceModel:

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Timing
        self._last_user_time: float = time.time()   # when the user last spoke
        self._last_orrin_time: float = time.time()  # when Orrin last responded
        self._session_start: float = time.time()
        # Nobody-here guard: this model describes "the current user's
        # engagement" — before anyone has EVER spoken this process, there is no
        # user to be distant. The 2026-07-02 run read 6,858 s of solitude as a
        # 0.95-pressure "distant" person and ignited the workspace on it 109+
        # times/hour while alone.
        self._ever_spoke: bool = False

        # Engagement quality history (rolling)
        self._quality_history: List[float] = [0.7]  # [0,1] per message
        self._response_gaps: List[float] = []        # user re-engagement gaps

        # Social confidence (how well interactions have been going)
        self._social_confidence: float = 0.6

        # Pressure
        self._pressure: float = _PRESSURE_FLOOR
        self._last_pattern: str = "present"
        self._door_event: Optional[Dict[str, Any]] = None

        # Cached USER_INPUT mtime for change detection. Seeded with the file's
        # current mtime: content left over from a previous life must not count
        # as this life's user speaking (the 2026-07-03 run minted a "person" at
        # boot from a stale file and spent 84% of its ignitions on the silence
        # that followed).
        self._last_input_mtime: float = self._current_input_mtime()

        self._thread = threading.Thread(
            target=self._run, name="orrin-social", daemon=True
        )

    def start(self) -> None:
        self._thread.start()

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            silence_s = time.time() - self._last_user_time
            pressure = self._pressure
            conf = self._social_confidence
            avg_quality = sum(self._quality_history[-5:]) / max(len(self._quality_history[-5:]), 1)

            pattern = self._pattern_for_silence(silence_s)
            if pattern != self._last_pattern:
                self._door_event = self._make_door_event(self._last_pattern, pattern, silence_s)
                self._last_pattern = pattern

            signal = None
            if pressure > _SIGNAL_THRESHOLD:
                signal = {
                    "source": "social_presence",
                    "content": self._pressure_message(silence_s, pattern, pressure),
                    "signal_strength": min(_SIGNAL_CEIL, pressure),
                    "tags": ["social", "presence", "internal"],
                    "social_pressure": pressure,
                    "social_pattern": pattern,
                }

            door_event = self._door_event
            self._door_event = None

            return {
                "pressure": round(pressure, 3),
                "silence_s": round(silence_s, 1),
                "pattern": pattern,
                "social_confidence": round(conf, 3),
                "avg_quality": round(avg_quality, 3),
                "signal": signal,
                "door_event": door_event,
            }

    def mark_user_spoke(self, quality: float = 0.7) -> None:
        with self._lock:
            self._ever_spoke = True
            now = time.time()
            gap = now - self._last_user_time
            old_pattern = self._pattern_for_silence(gap)
            self._last_user_time = now

            # Log re-engagement gap
            if gap > 30:
                self._response_gaps.append(gap)
                self._response_gaps = self._response_gaps[-20:]

            # Quality update: recent messages weighted more
            q = max(0.0, min(1.0, float(quality)))
            self._quality_history.append(q)
            self._quality_history = self._quality_history[-20:]

            # Social confidence nudges toward quality
            self._social_confidence = min(
                1.0,
                self._social_confidence * 0.85 + q * 0.15,
            )

            # Reset pressure — someone is here
            self._pressure = _PRESSURE_FLOOR
            if old_pattern != "present":
                self._door_event = self._make_door_event(old_pattern, "present", 0.0)
            self._last_pattern = "present"

    def mark_orrin_responded(self) -> None:
        with self._lock:
            self._last_orrin_time = time.time()

    # ------------------------------------------------------------------
    # Background loop

    def _run(self) -> None:
        time.sleep(5)
        while True:
            try:
                self._poll_user_input()
                self._accumulate_pressure()
            except Exception as _e:
                record_failure("social_presence.SocialPresenceModel._run", _e)
            time.sleep(_POLL_INTERVAL)

    @staticmethod
    def _current_input_mtime() -> float:
        try:
            from brain.paths import USER_INPUT
            p = Path(USER_INPUT)
            return p.stat().st_mtime if p.exists() else 0.0
        except Exception as _e:
            record_failure("social_presence.SocialPresenceModel._current_input_mtime", _e)
            return 0.0

    def _poll_user_input(self) -> None:
        """Detect new input by watching USER_INPUT mtime."""
        try:
            from brain.paths import USER_INPUT
            p = Path(USER_INPUT)
            if not p.exists():
                return
            mtime = p.stat().st_mtime
            if mtime > self._last_input_mtime + 0.5:
                content = p.read_text(encoding="utf-8", errors="replace").strip()
                if content:
                    self.mark_user_spoke()
                self._last_input_mtime = mtime
        except Exception as _e:
            record_failure("social_presence.SocialPresenceModel._poll_user_input", _e)

    def _accumulate_pressure(self) -> None:
        """Build social pressure proportional to silence duration."""
        with self._lock:
            if not self._ever_spoke:
                # No user has ever been here this process — there is no
                # engagement to model and no one to be "distant". Connection
                # hunger stays the drive engine's job; this stays at floor.
                self._pressure = _PRESSURE_FLOOR
                return
            silence_s = time.time() - self._last_user_time
            # Build pressure with silence, but curve it — first minutes matter more
            raw = _PRESSURE_BUILDUP * silence_s
            # Once the user has been gone over an hour ("distant"), the felt
            # state is absence, not mounting urgency — ease toward a lower
            # ceiling instead of climbing forever.
            ceil = _PRESSURE_CEIL_DISTANT if silence_s >= 3600 else 0.95
            target = min(ceil, _PRESSURE_FLOOR + raw * (1.0 - self._social_confidence * 0.3))
            # Smooth approach to target
            self._pressure = self._pressure + (target - self._pressure) * 0.1
            self._pressure = max(_PRESSURE_FLOOR, min(1.0, self._pressure))

    def _pressure_message(self, silence_s: float, pattern: str, pressure: float) -> str:
        if pattern == "distant":
            h = int(silence_s // 3600)
            return f"The conversation has been quiet for {h}h. I notice the silence. Social pressure at {pressure:.2f}."
        elif pattern == "absent":
            m = int(silence_s // 60)
            return f"No one has spoken in {m} minutes. The gap is starting to feel significant."
        else:
            return f"Social presence building — someone is nearby but quiet. Pressure: {pressure:.2f}."

    @staticmethod
    def _pattern_for_silence(silence_s: float) -> str:
        if silence_s < 60:
            return "present"
        if silence_s < 600:
            return "nearby"
        if silence_s < 3600:
            return "absent"
        return "distant"

    @staticmethod
    def _make_door_event(old: str, new: str, silence_s: float) -> Dict[str, Any]:
        direction = "arrival" if new == "present" else "departure"
        if new == "nearby":
            direction = "threshold_quiet"
        elif new in ("absent", "distant"):
            direction = "departure"
        content = (
            f"[social_boundary] User presence crossed the threshold: "
            f"{old} -> {new}."
        )
        return {
            "source": "social_presence",
            "content": content,
            "signal_strength": 0.62 if direction == "arrival" else 0.48,
            "tags": ["social", "presence", "door", "threshold_crossing", direction],
            "from_pattern": old,
            "to_pattern": new,
            "direction": direction,
            "silence_s": round(float(silence_s), 1),
        }
