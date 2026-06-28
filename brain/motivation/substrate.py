# brain/motivation/substrate.py
#
# Subsymbolic activation dynamics layer.  Runs as a background thread;
# does NOT call the LLM.  Enriches context for cognition layers above it.
#
# Interface (module-level):
#   inject_into_context(context)               → adds context["motivational_urges"]
#   evaluate_cycle_satisfaction(fn, reward)    → reward-driven drive satisfaction
#   get_current_urges(n=3)                     → top-N active urge dicts
#   satisfy_urge(urge_type, amount)            → manual satisfaction signal
#   update_dynamics(delta_t)                   → advance dynamics by delta_t seconds
from __future__ import annotations
from brain.core.runtime_log import get_logger

import random
import threading
import time
from typing import Any, Dict, List, Optional
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ENABLE_MOTIVATIONAL_SUBSTRATE: bool = True

_TICK_MIN: float = 3.0          # seconds between ticks (lower)
_TICK_MAX: float = 8.0          # seconds between ticks (upper)
_URGE_THRESHOLD: float = 0.38   # minimum activation to surface an urge
_SAVE_INTERVAL: float = 120.0   # seconds between persistence writes
_LOG_INTERVAL: float = 900.0    # seconds between long-memory log events

# ── Demand definitions ─────────────────────────────────────────────────────────
# Each entry: (baseline, rise_rate/s, fall_rate/s, focus_hint)
# rise_rate: how fast activation climbs when idle/deprived
# fall_rate: how fast activation decays when the drive is being satisfied
_DRIVE_DEFAULTS: Dict[str, tuple] = {
    "connection":          (0.30, 0.00020, 0.0080, "reach out — share something, ask something genuine"),
    "world_mastery":       (0.25, 0.00015, 0.0060, "investigate something you don't fully understand"),
    "competence":          (0.20, 0.00012, 0.0070, "do something and do it with care and skill"),
    "novelty_exploration_drive":   (0.35, 0.00018, 0.0065, "explore something unfamiliar or unexpected"),
    "autonomy":            (0.25, 0.00010, 0.0050, "choose your next action without being prompted"),
    "signal_stability": (0.40, 0.00008, 0.0090, "settle, reflect, find equilibrium before acting"),
    "restlessness":        (0.20, 0.00025, 0.0100, "move, act — break inertia with any purposeful step"),
}

# ── Cross-drive facilitation/inhibition ──────────────────────────────────────
# (source_drive, target_drive, effect_per_unit_activation)
# Positive = facilitation, negative = inhibition.  Effects are scaled by
# source's current activation and applied to target's current value each tick.
_CROSS_EFFECTS: List[tuple] = [
    ("connection",          "signal_stability",  +0.010),   # contact soothes
    ("connection",          "autonomy",             -0.008),   # yearning for connection slightly erodes felt autonomy
    ("novelty_exploration_drive",   "world_mastery",        +0.012),   # exploration_drive fuels mastery drive
    ("novelty_exploration_drive",   "restlessness",         +0.006),   # exploration_drive is also an itch
    ("restlessness",        "competence",           +0.010),   # restlessness pushes toward action/competence
    ("signal_stability", "restlessness",         -0.015),   # stability damps restlessness
    ("signal_stability", "autonomy",             +0.008),   # settled state supports chosen action
    ("competence",          "autonomy",             +0.006),   # skilled action reinforces agency
    ("world_mastery",       "novelty_exploration_drive",    -0.005),   # mastery slightly reduces raw novelty resource_demand
]

# ── Function → drive satisfaction mapping ────────────────────────────────────
# When a cognitive function fires, these drives absorb satisfaction scaled by
# the reward signal (amount = base * ((reward + 1) / 2)).
_FN_SATISFIES: Dict[str, List[tuple]] = {
    # (drive, base_amount)
    "speak":              [("connection", 0.35), ("signal_stability", 0.10)],
    "respond":            [("connection", 0.30), ("competence", 0.10)],
    "introspect":         [("signal_stability", 0.25), ("autonomy", 0.15)],
    "reflect":            [("signal_stability", 0.20), ("world_mastery", 0.10)],
    "look_outward":       [("world_mastery", 0.30), ("novelty_exploration_drive", 0.20)],
    "web_search":         [("world_mastery", 0.25), ("novelty_exploration_drive", 0.25)],
    "pursue_goal":        [("competence", 0.30), ("autonomy", 0.25)],
    "plan":               [("competence", 0.20), ("autonomy", 0.20)],
    "idle_consolidation_cycle":        [("novelty_exploration_drive", 0.30), ("signal_stability", 0.20)],
    "wonder":             [("novelty_exploration_drive", 0.35), ("world_mastery", 0.15)],
    "generate_intrinsic_goals": [("autonomy", 0.30), ("novelty_exploration_drive", 0.15)],
    "self_review":        [("competence", 0.15), ("signal_stability", 0.15)],
    "metacognition":      [("autonomy", 0.20), ("world_mastery", 0.10)],
    "memory_consolidate": [("signal_stability", 0.15), ("world_mastery", 0.10)],
}


# ── Singleton engine ──────────────────────────────────────────────────────────

_engine: Optional["_MotivationEngine"] = None
_engine_lock: threading.Lock = threading.Lock()


def _get_engine() -> "_MotivationEngine":
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = _MotivationEngine()
            _engine.start()
    return _engine


# ── Public API ────────────────────────────────────────────────────────────────

def inject_into_context(context: Dict[str, Any]) -> None:
    """Stamp top urges and drive snapshot into context.  No-op if disabled."""
    if not ENABLE_MOTIVATIONAL_SUBSTRATE:
        return
    try:
        eng = _get_engine()
        context["motivational_urges"] = eng.get_current_urges(n=3)
        context["drive_state_raw"] = eng.get_drive_snapshot()
    except Exception as _e:
        record_failure("substrate.inject_into_context", _e)


def evaluate_cycle_satisfaction(fn_name: str, reward: float) -> None:
    """Satisfy relevant drives based on which function fired and how well."""
    if not ENABLE_MOTIVATIONAL_SUBSTRATE:
        return
    try:
        _get_engine().reward_satisfy(fn_name, reward)
    except Exception as _e:
        record_failure("substrate.evaluate_cycle_satisfaction", _e)


def get_current_urges(n: int = 3) -> List[Dict[str, Any]]:
    if not ENABLE_MOTIVATIONAL_SUBSTRATE:
        return []
    try:
        return _get_engine().get_current_urges(n)
    except (ImportError, AttributeError):  # intentional: substrate engine unavailable → no urges
        return []


def satisfy_urge(urge_type: str, amount: float) -> None:
    if not ENABLE_MOTIVATIONAL_SUBSTRATE:
        return
    try:
        _get_engine().satisfy(urge_type, amount)
    except Exception as _e:
        record_failure("substrate.satisfy_urge", _e)


def update_dynamics(delta_t: float) -> None:
    """Advance dynamics explicitly (used in tests / manual calls)."""
    if not ENABLE_MOTIVATIONAL_SUBSTRATE:
        return
    try:
        _get_engine().update(delta_t)
    except Exception as _e:
        record_failure("substrate.update_dynamics", _e)


# ── Engine ────────────────────────────────────────────────────────────────────

class _MotivationEngine:

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Demand activations: {demand_name: float [0,1]}
        self._drives: Dict[str, float] = {
            name: baseline for name, (baseline, *_) in _DRIVE_DEFAULTS.items()
        }

        self._last_tick: float = time.time()
        self._last_save: float = 0.0
        self._last_log: float = 0.0

        self._thread = threading.Thread(
            target=self._run, name="orrin-motivation", daemon=True
        )

        self._load_state()

    def start(self) -> None:
        self._thread.start()

    # ── Background loop ────────────────────────────────────────────────────

    def _run(self) -> None:
        time.sleep(5.0)          # let brain boot first
        while True:
            try:
                now = time.time()
                delta_t = now - self._last_tick
                self._last_tick = now
                self.update(delta_t)
                self._maybe_save(now)
                self._maybe_log(now)
            except Exception as _e:
                record_failure("substrate._MotivationEngine._run", _e)
            time.sleep(random.uniform(_TICK_MIN, _TICK_MAX))

    # ── Core dynamics ──────────────────────────────────────────────────────

    def update(self, delta_t: float) -> None:
        """Advance all drives by delta_t seconds.  Pure math — no I/O."""
        with self._lock:
            drives = self._drives
            # Passive rise toward ceiling (deprivation accumulates)
            for name, (baseline, rise_rate, fall_rate, _) in _DRIVE_DEFAULTS.items():
                current = float(drives.get(name, baseline))
                # Drives naturally drift toward baseline if below, and continue
                # rising above baseline at the passive rise_rate up to ceiling.
                if current < baseline:
                    # below baseline: fast return
                    current += (baseline - current) * min(1.0, delta_t * fall_rate * 3)
                else:
                    # above baseline: slow passive rise (deprivation)
                    current = min(1.0, current + rise_rate * delta_t)
                drives[name] = max(0.0, min(1.0, current))

            # Cross-drive facilitation/inhibition
            deltas: Dict[str, float] = {}
            for src, tgt, coeff in _CROSS_EFFECTS:
                src_act = float(drives.get(src, 0.0))
                effect = coeff * src_act * delta_t
                deltas[tgt] = deltas.get(tgt, 0.0) + effect
            for name, delta in deltas.items():
                if name in drives:
                    drives[name] = max(0.0, min(1.0, drives[name] + delta))

            # Soft normalization toward a fixed total activation budget
            # (BEHAVIOR_FIX_PLAN Phase 4 / audit §10): independent clamps let
            # every drive pin at 1.0, giving the arbiter no gradient to choose
            # by. When total activation exceeds the budget, scale all drives
            # down proportionally — competition stays differentiable because
            # relative differences survive the rescale; saturation cannot.
            _budget = 0.6 * len(drives)   # mean activation capped at 0.6
            _total = sum(drives.values())
            if _total > _budget and _total > 0:
                _scale = _budget / _total
                for name in drives:
                    drives[name] = max(0.0, drives[name] * _scale)

    def satisfy(self, drive: str, amount: float) -> None:
        """Apply satisfaction (negative push) to a single drive."""
        with self._lock:
            if drive in self._drives:
                self._drives[drive] = max(0.0, self._drives[drive] - float(amount))

    def reward_satisfy(self, fn_name: str, reward: float) -> None:
        """Satisfy drives mapped to fn_name, scaled by reward."""
        mappings = _FN_SATISFIES.get(fn_name) or []
        if not mappings:
            # Partial match — substring search
            for key, maps in _FN_SATISFIES.items():
                if key in fn_name or fn_name in key:
                    mappings = maps
                    break
        if not mappings:
            return
        # Map reward [-1,1] → satisfaction scale [0.1, 1.0]
        scale = max(0.1, (float(reward) + 1.0) / 2.0)
        with self._lock:
            for demand_name, base_amount in mappings:
                if demand_name in self._drives:
                    self._drives[demand_name] = max(
                        0.0, self._drives[demand_name] - base_amount * scale
                    )

    # ── Urge sampling ──────────────────────────────────────────────────────

    def get_current_urges(self, n: int = 3) -> List[Dict[str, Any]]:
        """Return up to n urges for drives above threshold."""
        with self._lock:
            drives_snapshot = dict(self._drives)

        candidates: List[Dict[str, Any]] = []
        for name, activation in drives_snapshot.items():
            if activation < _URGE_THRESHOLD:
                continue
            focus_hint = _DRIVE_DEFAULTS[name][3]
            # Probabilistic gate: higher activation → higher chance of surfacing
            if random.random() > activation:
                continue
            candidates.append({
                "type":       name,
                "strength":   round(activation, 3),
                "focus_hint": focus_hint,
            })

        # Sort by strength descending; return top-n
        candidates.sort(key=lambda u: u["strength"], reverse=True)
        return candidates[:n]

    def get_drive_snapshot(self) -> Dict[str, float]:
        with self._lock:
            return {k: round(v, 3) for k, v in self._drives.items()}

    # ── Persistence ────────────────────────────────────────────────────────

    def _load_state(self) -> None:
        try:
            from brain.paths import DATA_DIR
            from brain.utils.json_utils import load_json
            p = DATA_DIR / "motivation_state.json"
            saved = load_json(str(p), default_type=dict) or {}
            drives = saved.get("drives") or {}
            with self._lock:
                for name in self._drives:
                    if name in drives:
                        self._drives[name] = max(0.0, min(1.0, float(drives[name])))
        except Exception as _e:
            record_failure("substrate._MotivationEngine._load_state", _e)

    def _maybe_save(self, now: float) -> None:
        if now - self._last_save < _SAVE_INTERVAL:
            return
        self._last_save = now
        try:
            from brain.paths import DATA_DIR
            from brain.utils.json_utils import save_json
            import datetime
            with self._lock:
                snapshot = dict(self._drives)
            save_json(
                str(DATA_DIR / "motivation_state.json"),
                {
                    "drives": {k: round(v, 4) for k, v in snapshot.items()},
                    "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                },
            )
        except Exception as _e:
            record_failure("substrate._MotivationEngine._maybe_save", _e)

    def _maybe_log(self, now: float) -> None:
        """Occasionally write high-activation drives to long memory."""
        if now - self._last_log < _LOG_INTERVAL:
            return
        self._last_log = now
        try:
            with self._lock:
                snapshot = dict(self._drives)
            notable = {k: round(v, 3) for k, v in snapshot.items() if v >= 0.60}
            if not notable:
                return
            desc = "; ".join(f"{k}={v}" for k, v in sorted(notable.items(), key=lambda x: -x[1]))
            from brain.cog_memory.long_memory import update_long_memory
            update_long_memory(
                f"[motivation] High-activation drives: {desc}",
                emotion="anticipation",
                event_type="motivation_state",
                importance=2,
                # Diagnostic write: must never surface as user-facing speech
                # (audit §4 caught this exact line spoken aloud).
                extra={"internal_telemetry": True},
            )
        except Exception as _e:
            record_failure("substrate._MotivationEngine._maybe_log", _e)
