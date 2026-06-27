# motivation/energy_orientation.py
#
# Energy-aware personality split: Orrin's cognitive mode shifts based on
# sustained activation_level/engagement state, not instantaneous emotional values.
#
# Scientific basis:
#   Yerkes & Dodson (1908) — inverted-U activation_level/performance curve.
#     Too low activation_level: disengaged, slow, inward. Optimal: peak outward performance.
#     Too high (negative): reactive, narrow, degraded executive function.
#     Three modes emerge naturally from this curve:
#       REST     = below the curve (resource_deficit, stagnation_signal, low motivation)
#       ACTIVE   = at/near peak (motivated, excited, curious)
#       REACTIVE = over the peak (risk_estimate + impasse_signal; high activation_level, negative valence)
#
#   Raichle, Gusnard et al. (2001) — Default Mode Network vs Task-Positive Network.
#     DMN (rest/introspection) and TPN (outward engagement) are anti-correlated.
#     resource_deficit and low motivation tip the balance toward DMN dominance.
#     High motivation and reward expectation activate TPN and suppress DMN.
#     → REST mode biases toward DMN functions: dreaming, autobiography, deep reflection.
#     → ACTIVE mode biases toward TPN functions: goal pursuit, outward engagement.
#
#   Baumeister, Bratslavsky, Muraven & Tice (1998) — Ego depletion / resource model.
#     Self-regulatory resources deplete with use. After depletion:
#     behavior becomes more automatic and emotional, less deliberate and ambitious.
#     → REST mode should narrow scope, reduce planning, prefer consolidation.
#
#   Robbins & Arnsten (2009) — Catecholamine modulation of prefrontal cortex.
#     Optimal reward_signal/gain_signal levels support goal-directed PFC function.
#     Too little (resource_deficit, low motivation) → PFC disengages → habit/DMN dominance.
#     Too much (risk_estimate, impasse_signal) → PFC destabilized → reactive, inflexible.
#     → REACTIVE mode: narrow focus, suppress long-term plans, prefer simple safe actions.
#
# SMOOTHING (why it matters):
#   Without smoothing, the mode would flip every cycle as emotions fluctuate.
#   Humans don't work that way. A tired person who briefly feels curious is still
#   tired. A motivated person who briefly worries is still in the flow.
#   Energy states shift on 8-15 cycle timescales in human cognition.
#   → EMA (exponential moving average) with alpha=0.12 ≈ 8-cycle half-life.
#   → Hysteresis gap: mode only changes when the new candidate consistently leads
#     the current mode by a margin, preventing boundary oscillation.
#
# Public API (unchanged for backward compat):
#   get_orientation(affect_state)           → EnergyOrientation (unsmoothed)
#   get_smoothed_orientation(context)          → EnergyOrientation (EMA-smoothed)
#   inject_into_context(context)              → stamps energy keys + surface text
#   energy_boost_scores(actions, state, bias, rest_mode) → per-function scores
#   ACTION_FUNCTIONS, REFLECT_FUNCTIONS        → frozensets
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.paths import ENERGY_MODE_FILE


# ── Smoothing constants ───────────────────────────────────────────────────────
EMA_ALPHA       = 0.12   # ~8-cycle half-life: slow, sticky, human-paced
HYSTERESIS_GAP  = 0.08   # mode only switches when new candidate leads by this
NEUTRAL_FLOOR   = 0.18   # all mode scores below this → stay neutral


# ── Function affinity sets ────────────────────────────────────────────────────

ACTION_FUNCTIONS: frozenset = frozenset({
    "pursue_committed_goal",
    "assess_goal_progress",
    "look_outward",
    "look_around",
    "seek_novelty",
    "generate_intrinsic_goals",
    "assess_innovation_outcomes",
    "search_own_files",
    "grep_files",
    "search_files",
    "plan_next_step",
    "thread_continue",
})

REFLECT_FUNCTIONS: frozenset = frozenset({
    "idle_consolidation_cycle",
    "reflection",
    "self_review",
    "narrative_update",
    "propose_value_revision",
    "plan_self_evolution",
    "reflect_on_self_beliefs",
    "metacog_flush",
    "mark_private",
    "introspect",
    "assess_goal_progress",   # dual-mode: keeps future plans honest
})

# Reflective functions are DISPREFERRED in high-energy mode, not locked out —
# DMN↔TPN anti-correlation is graded, not a switch (Raichle et al. 2001). An
# energized person can still turn inward, just less by default. propose_value_revision
# is deliberately NOT here: revising one's values is exactly the inward work that
# must stay reachable, and a standing penalty made self-belief revisions go empty.
_HIGH_ENERGY_SUPPRESS: frozenset = frozenset({
    "idle_consolidation_cycle", "self_review", "narrative_update", "reflection",
})

_REST_SUPPRESS: frozenset = frozenset({
    "pursue_committed_goal", "look_outward", "assess_innovation_outcomes",
})

# Reactive: anxious/frustrated — suppress everything ambitious
_REACTIVE_SUPPRESS: frozenset = frozenset({
    "pursue_committed_goal", "plan_self_evolution", "generate_intrinsic_goals",
    "look_outward", "seek_novelty", "assess_innovation_outcomes",
})

_REACTIVE_ALLOW: frozenset = frozenset({
    "reflection", "self_review", "reflect_on_directive",
})


# ── Data class ────────────────────────────────────────────────────────────────

@dataclass
class EnergyOrientation:
    energy_state: str   = "medium"
    action_bias:  float = 0.50
    rest_mode:    bool  = False
    mode:         str   = "neutral"   # "active" | "rest" | "reactive" | "neutral"
    motivation:   float = 0.5
    resource_deficit:      float = 0.3
    stagnation_signal:      float = 0.2
    surface_text: str   = ""


# ── Mode surface text ─────────────────────────────────────────────────────────

_MODE_SURFACE = {
    "active":   "Energy mode: active — outward, capable, ready to reach further.",
    "rest":     "Energy mode: rest — consolidating, introspective, lower reach.",
    "reactive": "Energy mode: reactive — anxious activation_level; keep scope narrow and safe.",
    "neutral":  "",
}

_MODE_NOTE = {
    "active":   (
        "High energy state (motivation↑, exploration_drive↑). "
        "This is a good time for goal pursuit, outward engagement, and ambitious cognition."
    ),
    "rest":     (
        "Rest/low-energy state (resource_deficit↑, motivation↓). "
        "This is a good time for deep reflection, value alignment, dreaming, and autobiography. "
        "Don't force action — let insight emerge."
    ),
    "reactive": (
        "Reactive state (risk_estimate↑ or impasse_signal↑). "
        "activation_level is high but negatively valenced. Scope should narrow: prefer simple, "
        "safe cognition over long-horizon planning."
    ),
    "neutral":  "",
}


# ── Raw score computation ─────────────────────────────────────────────────────

def _raw_scores(affect_state: Dict[str, Any]) -> Dict[str, float]:
    """
    Compute per-mode raw signal scores [0.0, 1.0] from emotional state.

    Active: catecholamine-rich (Robbins & Arnsten 2009); driven by
      motivation, excitement, exploration_drive, positive_valence.

    Rest: resource depleted (Baumeister 1998); driven by resource_deficit, negative_valence,
      stagnation_signal; anti-driven by motivation.

    Reactive: Yerkes-Dodson over-peak; driven by risk_estimate + impasse_signal;
      damped by motivation (if motivation is intact, risk_estimate may be productive).
    """
    es = affect_state or {}
    core = es.get("core_signals", es) or {}

    def _g(k):
        return max(0.0, min(1.0, float(core.get(k, es.get(k, 0)) or 0)))

    mot = _g("motivation")
    exc = _g("excitement")
    cur = _g("exploration_drive")
    positive_valence = _g("positive_valence")
    fat = _g("resource_deficit")
    sad = _g("negative_valence")
    bor = _g("stagnation_signal")
    anx = _g("risk_estimate")
    fru = _g("impasse_signal")

    active   = mot * 0.35 + exc * 0.30 + cur * 0.25 + positive_valence * 0.10 - fat * 0.25
    rest     = fat * 0.45 + sad * 0.25 + bor * 0.20 + max(0.0, 0.25 - mot) * 0.10
    reactive = anx * 0.50 + fru * 0.35 - mot * 0.15

    return {
        "active":   max(0.0, min(1.0, active)),
        "rest":     max(0.0, min(1.0, rest)),
        "reactive": max(0.0, min(1.0, reactive)),
    }


# ── EMA smoothing ─────────────────────────────────────────────────────────────

def _update_ema(raw: Dict[str, float], prev: Dict[str, float]) -> Dict[str, float]:
    return {
        k: round(EMA_ALPHA * raw.get(k, 0.0) + (1.0 - EMA_ALPHA) * prev.get(k, 0.0), 4)
        for k in ("active", "rest", "reactive")
    }


def _decide_mode(ema: Dict[str, float], current: str) -> str:
    """
    Choose mode from EMA scores with hysteresis.

    Neutral is the default — a mode must exceed NEUTRAL_FLOOR to activate.
    A mode that's already active requires HYSTERESIS_GAP lead from a competitor
    before yielding — prevents oscillation near mode boundaries.
    """
    best = max(ema, key=lambda k: ema[k])
    best_score = ema[best]

    if best_score < NEUTRAL_FLOOR:
        return "neutral"

    if current == "neutral":
        if best_score >= NEUTRAL_FLOOR + HYSTERESIS_GAP:
            return best
        return "neutral"

    curr_score = ema.get(current, 0.0)
    if best != current and best_score >= curr_score + HYSTERESIS_GAP:
        return best
    return current


# ── Persistence ───────────────────────────────────────────────────────────────

def _load() -> Dict[str, Any]:
    data = load_json(ENERGY_MODE_FILE, default_type=dict)
    return data if isinstance(data, dict) else {}


def _save(state: Dict[str, Any]) -> None:
    save_json(ENERGY_MODE_FILE, state)


# ── Public API ────────────────────────────────────────────────────────────────

def get_orientation(affect_state: Dict[str, Any]) -> EnergyOrientation:
    """
    Unsmoothed orientation from a single emotional state snapshot.
    Kept for backward compat. Prefer get_smoothed_orientation(context).
    """
    raw = _raw_scores(affect_state)
    es = affect_state or {}

    mot = max(0.0, min(1.0, float(es.get("motivation", 0.5) or 0.5)))
    fat = max(0.0, min(1.0, float(es.get("resource_deficit",    0.3) or 0.3)))
    bor = max(0.0, min(1.0, float(es.get("stagnation_signal",    0.2) or 0.2)))

    best = max(raw, key=lambda k: raw[k])
    mode = best if raw[best] >= NEUTRAL_FLOOR else "neutral"

    raw_signal  = mot - 1.2 * fat - 0.5 * bor
    action_bias = max(0.0, min(1.0, 0.5 + raw_signal * 0.45))

    energy_state = "high" if action_bias >= 0.65 else ("low" if action_bias <= 0.35 else "medium")
    rest_mode    = fat > 0.60 or (fat > 0.45 and mot < 0.30) or (mot < 0.20 and bor > 0.50)

    return EnergyOrientation(
        energy_state=energy_state,
        action_bias=round(action_bias, 3),
        rest_mode=rest_mode,
        mode=mode,
        motivation=mot,
        resource_deficit=fat,
        stagnation_signal=bor,
        surface_text=_MODE_SURFACE.get(mode, ""),
    )


def get_smoothed_orientation(context: Dict[str, Any]) -> EnergyOrientation:
    """
    EMA-smoothed orientation. Loads previous EMA state, updates it from the
    current emotional state, applies hysteresis before switching modes.
    Persists the new EMA state for the next cycle.

    This is the human-accurate path: energy modes shift slowly, stay sticky,
    and don't flicker with every emotional fluctuation.
    """
    es  = context.get("affect_state") or {}
    raw = _raw_scores(es)

    state    = _load()
    prev_ema = state.get("ema", {"active": 0.0, "rest": 0.0, "reactive": 0.0})
    ema      = _update_ema(raw, prev_ema)
    current  = state.get("mode", "neutral")
    mode     = _decide_mode(ema, current)

    # Derive EnergyOrientation fields from mode
    _mode_to_state = {"active": "high", "rest": "low", "reactive": "medium", "neutral": "medium"}
    _mode_to_bias  = {"active": 0.75,   "rest": 0.25,  "reactive": 0.40,    "neutral": 0.50}
    _mode_to_rest  = {"active": False,  "rest": True,  "reactive": False,   "neutral": False}

    energy_state = _mode_to_state[mode]
    action_bias  = _mode_to_bias[mode]
    rest_mode    = _mode_to_rest[mode]

    # Extract raw values for logging / dataclass
    core = (es.get("core_signals") or es) or {}
    def _g(k): return max(0.0, min(1.0, float(core.get(k, es.get(k, 0)) or 0)))
    mot = _g("motivation"); fat = _g("resource_deficit"); bor = _g("stagnation_signal")

    surface = _MODE_SURFACE.get(mode, "")

    state.update({
        "mode":        mode,
        "ema":         ema,
        "raw":         raw,
        "updated_ts":  datetime.now(timezone.utc).isoformat(),
    })
    _save(state)

    log_private(
        f"[energy] mode={mode} ema=act:{ema['active']:.3f} "
        f"rst:{ema['rest']:.3f} rct:{ema['reactive']:.3f} "
        f"(mot={mot:.2f} fat={fat:.2f} bor={bor:.2f})"
    )

    return EnergyOrientation(
        energy_state=energy_state,
        action_bias=action_bias,
        rest_mode=rest_mode,
        mode=mode,
        motivation=mot,
        resource_deficit=fat,
        stagnation_signal=bor,
        surface_text=surface,
    )


def inject_into_context(context: Dict[str, Any]) -> EnergyOrientation:
    """
    Compute smoothed orientation and stamp it on context.

    Keys written:
      context["energy_mode"]             → "active"|"rest"|"reactive"|"neutral"
      context["energy_state"]            → "high"|"medium"|"low"
      context["action_vs_reflect_bias"]  → float 0.0–1.0
      context["_rest_mode"]              → bool
      context["_energy_mode_text"]       → surface text for inner loop
      context["_rest_mode_note"]         → longer note (when rest_mode=True)
    """
    orientation = get_smoothed_orientation(context)

    context["energy_mode"]            = orientation.mode
    context["energy_state"]           = orientation.energy_state
    context["action_vs_reflect_bias"] = orientation.action_bias
    context["_rest_mode"]             = orientation.rest_mode
    context["_energy_mode_text"]      = orientation.surface_text

    note = _MODE_NOTE.get(orientation.mode, "")
    if note:
        context["_rest_mode_note"] = note
    else:
        context.pop("_rest_mode_note", None)

    return orientation


# ── Score helpers (used by select_function.py) ────────────────────────────────

def energy_boost_scores(
    actions: list,
    energy_state: str,
    action_bias: float,
    rest_mode: bool,
) -> Dict[str, float]:
    """
    Per-function additive score adjustments based on energy state.
    Values in [-0.25, +0.25].

    select_function.py calls this with context["energy_state"],
    context["action_vs_reflect_bias"], context["_rest_mode"] — all set by
    inject_into_context() which must run before select_function() each cycle.
    """
    boosts: Dict[str, float] = {}

    if rest_mode or energy_state == "low" or action_bias < 0.35:
        for fn in actions:
            if fn in REFLECT_FUNCTIONS:
                boosts[fn] = 0.24
            elif fn in _REST_SUPPRESS:
                boosts[fn] = -0.10

    elif energy_state == "high" or action_bias > 0.65:
        for fn in actions:
            if fn in ACTION_FUNCTIONS:
                boosts[fn] = 0.24
            elif fn in _HIGH_ENERGY_SUPPRESS:
                # Softened from -0.14: a nudge away from reflection, not a lockout.
                # Inward work keeps a fighting chance in active mode (graded DMN/TPN).
                boosts[fn] = -0.06

    elif action_bias <= 0.45:
        # Reactive range: medium energy_state but inward bias (reactive mode)
        for fn in actions:
            if fn in _REACTIVE_SUPPRESS:
                boosts[fn] = -0.18
            elif fn in _REACTIVE_ALLOW:
                boosts[fn] = 0.12

    elif action_bias > 0.58:
        for fn in actions:
            if fn in ACTION_FUNCTIONS:
                boosts[fn] = 0.10
    elif action_bias < 0.42:
        for fn in actions:
            if fn in REFLECT_FUNCTIONS:
                boosts[fn] = 0.10

    return boosts
