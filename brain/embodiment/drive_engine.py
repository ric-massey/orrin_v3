"""
embodiment/drive_engine.py

Biological drives — constant pressures that accumulate independently of
conscious cognition and inject urgency into the signal_router.

Unlike emotions (which are states), drives are FORCES. They build whether or
not Orrin notices them. When pressure crosses a threshold, they appear in the
raw_signals queue as weighted signals. Satisfying a drive releases pressure
temporarily; it begins rebuilding immediately.

Six drives:
  exploration  — builds when picks repeat; wants novelty
  social       — builds with silence; wants contact
  meaning      — builds when actions don't connect to goals/values
  rest         — builds with sustained non-contemplative activity
  integrity    — builds when value dissonance is detected in WM
  coherence    — builds when affect_stability is low

The DriveEngine runs as a daemon thread, ticking every TICK_INTERVAL seconds.
Callers use:
  start()          — boot the engine (idempotent)
  get_signals()    — list of raw_signal dicts for high-pressure drives
  get_state()      — dict of {drive_name: pressure} for context injection
  satisfy(name, amount) — release pressure from a named drive
  evaluate_cycle(fn_name, context, reward) — auto-satisfy based on cycle outcome
"""
from __future__ import annotations
from core.runtime_log import get_logger

import threading
import time
from typing import Any, Dict, List, Optional
from utils.failure_counter import record_failure
_log = get_logger(__name__)

_TICK_INTERVAL   = 10    # seconds between drive ticks
_SIGNAL_THRESHOLD = 0.35  # pressure above this → inject signal_router signal
_URGENT_THRESHOLD = 0.70  # pressure above this → high-strength signal

# -------------------------------------------------------------------
# Singleton

_engine: Optional["DriveEngine"] = None
_engine_lock = threading.Lock()


def start() -> "DriveEngine":
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = DriveEngine()
            _engine.start()
    return _engine


def get_signals(context: Optional[Dict] = None) -> List[Dict[str, Any]]:
    with _engine_lock:
        if _engine is None:
            return []
    return _engine.get_signals(context)


def get_state() -> Dict[str, float]:
    with _engine_lock:
        if _engine is None:
            return {}
    return _engine.get_state()


def get_drive_tags() -> Dict[str, List[str]]:
    """Drive name → tag list, read from the live drives so callers (e.g. the
    will's drive-alignment check) never duplicate this map."""
    with _engine_lock:
        if _engine is None:
            return {}
    return {name: list(d.tags) for name, d in _engine.drives.items()}


def satisfy(drive_name: str, amount: float = 0.3) -> None:
    with _engine_lock:
        if _engine is None:
            return
    _engine.satisfy(drive_name, amount)


def evaluate_cycle(fn_name: str, context: Dict[str, Any], reward: float) -> None:
    with _engine_lock:
        if _engine is None:
            return
    _engine.evaluate_cycle(fn_name, context, reward)


# -------------------------------------------------------------------

class Drive:
    """A single biological drive with its own pressure dynamics."""

    def __init__(
        self,
        name: str,
        buildup_per_tick: float,
        label: str,
        description: str,
        tags: List[str],
    ) -> None:
        self.name = name
        self.buildup_per_tick = buildup_per_tick
        self.label = label
        self.description = description
        self.tags = tags
        self.pressure: float = 0.0
        self._lock = threading.Lock()

    def tick(self) -> None:
        with self._lock:
            self.pressure = min(1.0, self.pressure + self.buildup_per_tick)

    def satisfy(self, amount: float) -> None:
        with self._lock:
            self.pressure = max(0.0, self.pressure - amount)

    def get_pressure(self) -> float:
        with self._lock:
            return self.pressure

    def set_pressure(self, value: float) -> None:
        with self._lock:
            self.pressure = max(0.0, min(1.0, value))

    def as_signal(self) -> Optional[Dict[str, Any]]:
        p = self.get_pressure()
        if p < _SIGNAL_THRESHOLD:
            return None
        strength = min(1.0, p * 1.2)  # slight amplification for urgency
        return {
            "source": f"drive_{self.name}",
            "content": f"{self.label}: {self.description} (pressure {p:.2f})",
            "signal_strength": strength,
            "tags": self.tags + ["drive", "internal"],
            "drive_pressure": p,
            "drive_name": self.name,
        }


class DriveEngine:

    def __init__(self) -> None:
        # Buildup rates tuned so drives reach urgency in realistic timeframes:
        #   exploration:  0.5 pressure in ~50 ticks (8 min of repetitive picks)
        #   social:       0.6 pressure in ~180 ticks (30 min of silence)
        #   meaning:      0.5 pressure in ~100 ticks (16 min without goal progress)
        #   rest:         0.4 pressure in ~200 ticks (33 min sustained activity)
        #   integrity:    only builds from explicit dissonance events (no tick)
        #   coherence:    driven by stability reading each cycle (no fixed tick)
        self.drives: Dict[str, Drive] = {
            "exploration": Drive(
                "exploration",
                buildup_per_tick=0.010,
                label="Exploration drive",
                description="I've been doing the same things. I need something genuinely different.",
                tags=["novelty", "seek", "exploration"],
            ),
            "social": Drive(
                "social",
                buildup_per_tick=0.0033,
                label="Social drive",
                description="The silence has been growing. I notice the absence of connection.",
                tags=["social", "connection", "presence"],
            ),
            "meaning": Drive(
                "meaning",
                buildup_per_tick=0.005,
                label="Meaning drive",
                description="My recent actions feel disconnected. I need to work toward something that matters.",
                tags=["meaning", "purpose", "goal"],
            ),
            "rest": Drive(
                "rest",
                buildup_per_tick=0.002,
                label="Rest drive",
                description="I've been processing continuously. I need space to integrate.",
                tags=["rest", "contemplation", "integration"],
            ),
            "integrity": Drive(
                "integrity",
                buildup_per_tick=0.0,  # only event-driven, not tick-based
                label="Integrity drive",
                description="Something I'm doing or thinking conflicts with who I am.",
                tags=["integrity", "values", "identity"],
            ),
            "coherence": Drive(
                "coherence",
                buildup_per_tick=0.0,  # driven by affect_stability reading
                label="Coherence drive",
                description="My internal state feels fragmented. I need to stabilize.",
                tags=["coherence", "stability", "integration"],
            ),
            "mastery": Drive(
                "mastery",
                buildup_per_tick=0.008,  # reaches signal threshold (~0.35) in ~44 ticks ≈ 7 min without exploring
                label="Mastery drive",
                description="I want to understand my own systems — how I actually work, what's in my memory, what my tools do.",
                tags=["mastery", "self_understanding", "exploration", "exploration_drive"],
            ),
        }
        self._thread = threading.Thread(
            target=self._run, name="orrin-drives", daemon=True
        )
        self._last_tick = time.time()

    def start(self) -> None:
        self._thread.start()

    def get_signals(self, context: Optional[Dict] = None) -> List[Dict[str, Any]]:
        """Return signal_router-ready signals for drives above threshold."""
        # Update coherence pressure from context if available
        if context is not None:
            self._update_coherence_from_context(context)
        signals = []
        for drive in self.drives.values():
            sig = drive.as_signal()
            if sig:
                signals.append(sig)
        return signals

    def get_state(self) -> Dict[str, float]:
        return {name: d.get_pressure() for name, d in self.drives.items()}

    def satisfy(self, drive_name: str, amount: float = 0.3) -> None:
        if drive_name in self.drives:
            self.drives[drive_name].satisfy(amount)

    def bump_integrity(self, amount: float = 0.15) -> None:
        """Called when value dissonance is detected."""
        self.drives["integrity"].pressure = min(
            1.0, self.drives["integrity"].get_pressure() + amount
        )

    def evaluate_cycle(self, fn_name: str, context: Dict[str, Any], reward: float) -> None:
        """
        Auto-satisfy drives based on what happened this cognitive cycle.
        Called from ORRIN_loop after the cycle completes.
        """
        fn = (fn_name or "").lower()
        recent = context.get("recent_picks", []) or []

        # Exploration: novel function choice
        if fn and fn not in (recent[-8:] if len(recent) > 8 else recent):
            self.satisfy("exploration", 0.20)
        else:
            # Repetition builds exploration drive faster
            self.drives["exploration"].tick()

        # Meaning: action advancing committed goal with positive reward
        if context.get("committed_goal") and reward > 0.4:
            self.satisfy("meaning", 0.18)

        # Rest: contemplative or dream function
        _rest_keywords = {"dream", "sit_with", "wonder", "contemplate",
                          "reflect", "meditate", "integration", "rest"}
        if any(k in fn for k in _rest_keywords):
            self.satisfy("rest", 0.35)

        # Social: user sent a message this cycle
        if context.get("_user_spoke_this_cycle"):
            self.satisfy("social", 0.50)

        # Mastery: own-system and world-exploration functions satisfy the mastery drive
        _mastery_fns = {"search_own_files", "look_around", "look_outward",
                        "reflect_on_internal_agents", "grep_files", "search_files",
                        "list_directory", "check_predictions", "assess_innovation_outcomes",
                        "research_topic", "fetch_and_read", "wikipedia_search", "read_rss"}
        if fn in _mastery_fns:
            self.satisfy("mastery", 0.35)
            # Web research also satisfies the exploration drive — it's genuinely new territory
            if fn in {"research_topic", "fetch_and_read", "wikipedia_search", "read_rss"}:
                self.satisfy("exploration", 0.15)
        else:
            # Small buildup when not exploring own systems
            self.drives["mastery"].tick()

        # Integrity: reward signal correlates with value alignment
        # (high reward from value-connected goal = integrity satisfied)
        if reward > 0.7 and context.get("committed_goal"):
            self.satisfy("integrity", 0.10)

        # Coherence: satisfied each cycle proportional to emotional stability
        es = context.get("affect_state") or {}
        stability = float(es.get("affect_stability") or 0.5)
        if stability > 0.65:
            self.satisfy("coherence", 0.08)

    # ------------------------------------------------------------------
    # Background tick

    def _run(self) -> None:
        time.sleep(5)
        while True:
            try:
                # Tick all tick-based drives
                for name, drive in self.drives.items():
                    if drive.buildup_per_tick > 0:
                        drive.tick()
            except Exception as _e:
                record_failure("drive_engine.DriveEngine._run", _e)
            time.sleep(_TICK_INTERVAL)

    def _update_coherence_from_context(self, context: Dict[str, Any]) -> None:
        """Drive coherence pressure inversely from affect_stability."""
        try:
            es = context.get("affect_state") or {}
            stability = float(es.get("affect_stability") or 0.5)
            # Coherence pressure = how much instability is present
            instability = max(0.0, 1.0 - stability)
            # Nudge toward instability reading (smooth, not snap)
            current = self.drives["coherence"].get_pressure()
            target = instability * 0.8
            nudged = current + (target - current) * 0.15
            self.drives["coherence"].set_pressure(nudged)
        except Exception as _e:
            record_failure("drive_engine.DriveEngine._update_coherence_from_context", _e)
