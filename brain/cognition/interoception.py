# brain/cognition/interoception.py
#
# Interoceptive cost prediction — proactive/allostatic resource management.
# See docs/proactive_resource_plan.md.
#
# PHASE 1 STATUS: cost-learning + FELT prediction error (C1).
# Learns the expected execution cost of each cognitive function and computes the
# prediction error between expected and actual cost — an active-inference view of
# "stress" (surprise = interoceptive prediction error). Phase 1 adds a SMALL,
# flag-gated affect nudge: a surprisingly-costly act feels like strain
# (resource_deficit ↑), a surprisingly-cheap one like ease (↓), via the
# AffectArbiter. Still NOT applied: EVC gating (→ Phase 3) and the allostatic
# set-point τ (→ Phase 2) are computed and logged here as would-be values only.
#
# Scientific grounding (embedded per the plan's "sources in code" rule):
#   Friston (2010) — The free-energy principle: a unified brain theory? Stress is
#     interoceptive prediction error; the agent minimizes expected surprise.
#   Seth (2013) — Interoceptive inference, emotion, and the embodied self.
#   Barrett & Simmons (2015) — Interoceptive predictions in the brain.
#   Shenhav, Botvinick & Cohen (2013) — Expected Value of Control (the would-be
#     EVC logged here; applied in Phase 3).
#   Sterling (2012); McEwen & Wingfield (2003) — Allostasis / allostatic load (the
#     would-be context-adaptive set-point τ logged here; applied in Phase 2).
from __future__ import annotations

from typing import Any, Dict, Optional

from brain.core.runtime_log import get_logger
from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_private
from brain.utils.env import env_bool
from brain.paths import DATA_DIR

_log = get_logger(__name__)

_MODEL_FILE = DATA_DIR / "interoceptive_model.json"
_EMA_ALPHA = 0.20          # learning rate for expected-cost EMA
_DEFAULT_COST_MS = 250.0   # cold-start prior for an unknown / mid function

# ── Phase 1: felt prediction error (C1 affect nudge) ──────────────────────────
# An act that costs MORE than expected feels like strain (resource_deficit ↑); one
# that costs LESS feels like ease (↓). The nudge is the SIGNED surprise, not |PE|.
# Asymmetric: strain registers more than ease (negativity bias; also prevents an
# energy-refund exploit from chaining cheap-surprising acts). Routed through the
# AffectArbiter (capped/budgeted). As the EMA learns, surprise → 0, so nudges fade
# to ~0 at equilibrium — known effort stops feeling like strain (active inference).
# Gated by ORRIN_INTEROCEPTIVE_AFFECT (default on; set 0 to disable).
_NUDGE_GAIN_UP = 0.000015     # per ms of costlier-than-expected (strain)
_NUDGE_GAIN_DOWN = 0.000006   # per ms of cheaper-than-expected (ease) — gentler
_NUDGE_CLAMP = 0.012          # max |Δresource_deficit| per act
_NUDGE_MIN = 0.0005           # ignore negligible surprises


def _affect_enabled() -> bool:
    return env_bool("ORRIN_INTEROCEPTIVE_AFFECT", True)

# Class priors (ms) for cold-start — this IS dual_process_loop's I9 "automaticity
# is cheap": procedural/gathering steps are predicted cheap, deliberate/effortful
# ones dear. Resolved lazily to avoid import cycles.
_PROCEDURAL_PRIOR_MS = 120.0
_DELIBERATE_PRIOR_MS = 600.0

_model_cache: Optional[Dict[str, Any]] = None


def _load_model() -> Dict[str, Any]:
    global _model_cache
    if _model_cache is None:
        m = load_json(_MODEL_FILE, default_type=dict)
        _model_cache = m if isinstance(m, dict) else {}
    return _model_cache


def _save_model(m: Dict[str, Any]) -> None:
    global _model_cache
    _model_cache = m
    try:
        save_json(_MODEL_FILE, m)
    except Exception as _e:
        _log.warning("interoceptive model save failed: %s", _e)


def _class_prior(fn: str) -> float:
    """Cold-start expected cost from the function's class (I9: procedural cheap,
    deliberate dear). Fail-safe to a mid prior."""
    try:
        from brain.cognition.planning.step_execution import is_procedural
        if is_procedural(fn):
            return _PROCEDURAL_PRIOR_MS
    except Exception:
        pass
    try:
        from brain.motivation.energy_orientation import REFLECT_FUNCTIONS
        from brain.cognition.cognitive_cost import is_introspective
        if fn in REFLECT_FUNCTIONS or is_introspective(fn):
            return _DELIBERATE_PRIOR_MS
    except Exception:
        pass
    return _DEFAULT_COST_MS


def predict_cost(fn: str, context: Optional[Dict[str, Any]] = None) -> float:
    """Expected execution cost (ms) for `fn`: the learned EMA, or the class prior
    when unseen. Read-only."""
    if not fn:
        return _DEFAULT_COST_MS
    entry = _load_model().get(fn)
    if isinstance(entry, dict) and entry.get("ema") is not None:
        try:
            return float(entry["ema"])
        except (TypeError, ValueError):
            pass
    return _class_prior(fn)


def record_cost(fn: str, latency_ms: float) -> float:
    """Update the expected-cost EMA for `fn` from a measured latency and return the
    prediction error (|actual − expected|, Friston PE). OBSERVE-ONLY: learns and
    returns; never nudges affect in Phase 0."""
    if not fn:
        return 0.0
    try:
        latency_ms = float(latency_ms)
    except (TypeError, ValueError):
        return 0.0
    m = _load_model()
    prev = predict_cost(fn)
    pe = abs(latency_ms - prev)
    entry = m.get(fn) if isinstance(m.get(fn), dict) else {}
    new_ema = (1.0 - _EMA_ALPHA) * prev + _EMA_ALPHA * latency_ms
    entry.update({"ema": round(new_ema, 2), "n": int(entry.get("n", 0)) + 1,
                  "last": round(latency_ms, 2)})
    m[fn] = entry
    _save_model(m)
    return round(pe, 2)


def _avg_reward(fn: str) -> float:
    """Per-function avg_reward from decision_stats (the EVC reward term)."""
    try:
        stats = load_json(DATA_DIR / "decision_stats.json", default_type=dict)
        if isinstance(stats, dict) and isinstance(stats.get(fn), dict):
            return float(stats[fn].get("avg_reward", 0.5) or 0.5)
    except Exception:
        pass
    return 0.5


def would_be_evc(fn: str, context: Dict[str, Any], lam: float = 0.0006) -> float:
    """The Expected Value of Control Orrin WOULD compute for `fn` this cycle
    (Shenhav et al. 2013): avg_reward − λ·expected_cost·(1+resource_deficit).
    Phase 0 logs it; Phase 3 applies it. `lam` scales ms→reward units."""
    rd = 0.0
    try:
        rd = float((context.get("affect_state") or {}).get("resource_deficit", 0.0) or 0.0)
    except Exception:
        pass
    return round(_avg_reward(fn) - lam * predict_cost(fn, context) * (1.0 + rd), 4)


# ── Phase 3: EVC selection gating (C2) ────────────────────────────────────────
# The genuinely NEW, non-double-counted EVC contribution is a COST penalty: Orrin
# doesn't otherwise price compute cost into selection. Reward is already factored
# (select_function's avg_reward fade) and depletion-MODE is already in
# energy_boost_scores — so EVC adds ONLY the cost dimension: expensive functions are
# down-weighted, DISCOUNTED by their payoff (high-reward cost is "worth it"), and
# mildly scaled by depletion (control costs more when tired — Shenhav et al. 2013).
# Gated by ORRIN_EVC_GATING (default on). Start with a small λ; A3 must confirm
# effortful cognition isn't starved.
_EVC_LAMBDA = 0.12        # strength of the cost penalty
_EVC_COST_SCALE = 600.0   # ms; the deliberate-class prior → normalizes cost to ~[0,1]
_EVC_CAP = 0.20           # max |penalty| per candidate


def _evc_enabled() -> bool:
    return env_bool("ORRIN_EVC_GATING", True)


# C5 corrigibility (proactive_resource_plan.md): the energy/EVC layer must NEVER
# suppress communication with the user or the shutdown path. These functions are
# already excluded from bandit selection (select_function._ALWAYS_EXCLUDE), but
# guard here too (belt-and-suspenders) so no future routing can let "I'm tired"
# override a reply or a directive. Soares et al. (2015) corrigibility.
_NEVER_GATE = frozenset({
    "speak", "respond", "respond_to_user", "user_response", "ask_user", "reply",
})


def evc_selection_adjust(fn: str, avg_reward: float, context: Dict[str, Any]) -> float:
    """Phase 3 (C2): the EVC adjustment to `fn`'s selection score — a payoff-
    discounted, depletion-scaled COST penalty (≤ 0). Shenhav, Botvinick & Cohen
    (2013). Returns 0 when disabled or for corrigibility-critical functions (C5).
    Cost & reward are NOT re-added (handled elsewhere); only the cost dimension is
    contributed here (no double-count)."""
    if not _evc_enabled() or not fn or fn in _NEVER_GATE:
        return 0.0
    try:
        cost_norm = min(1.0, predict_cost(fn, context) / _EVC_COST_SCALE)
        reward_factor = max(0.0, 1.0 - float(avg_reward))   # low payoff → full penalty
        rd = float((context.get("affect_state") or {}).get("resource_deficit", 0.0) or 0.0)
        penalty = _EVC_LAMBDA * cost_norm * reward_factor * (1.0 + 0.5 * rd)
        return -round(min(_EVC_CAP, penalty), 4)
    except Exception:
        return 0.0


def setpoint_candidate(context: Dict[str, Any]) -> float:
    """The allostatic recovery target τ Orrin WOULD set from context (Sterling
    2012). Phase 0 logs it; Phase 2 applies it (replacing the fixed 0.15). Lower τ
    when idle (recover deeper); higher τ during a live exchange / critical state
    (permit acute burn). Bounded [0.10, 0.45]."""
    tau = 0.15  # current fixed baseline
    try:
        if context.get("_tier1_critical"):
            tau = 0.40
        elif (context.get("latest_user_input") or "").strip():
            tau = 0.30
        elif context.get("_rest_mode") or context.get("energy_mode") == "rest":
            tau = 0.12
    except Exception:
        pass
    return max(0.10, min(0.45, tau))


def _allostatic_enabled() -> bool:
    return env_bool("ORRIN_ALLOSTATIC_SETPOINT", True)


def allostatic_setpoint(context: Dict[str, Any], state: Dict[str, Any]) -> float:
    """Phase 2 (C3): the context-adaptive recovery target τ for resource_deficit,
    REPLACING the fixed 0.15 baseline. Recover deeper when idle; tolerate more
    deficit during a live / critical exchange — predictive regulation, not a static
    set-point (Sterling 2012, allostasis). Sustained high deficit accrues
    ALLOSTATIC LOAD that forces τ back down (McEwen & Wingfield 2003), so "permit
    acute burn" can never become a permanent run-ragged state. Smoothed (C4) so it
    doesn't thrash. Returns τ ∈ [0.10, 0.45]; falls back to 0.15 when disabled or
    context/state is absent. Mutates `state` to persist allostatic load + smoothed τ."""
    if not _allostatic_enabled() or not isinstance(context, dict) or not isinstance(state, dict):
        return 0.15
    tau = setpoint_candidate(context)
    rd = float(state.get("resource_deficit", 0.15) or 0.15)
    # Allostatic load: accrues while running hot, recovers faster than it builds.
    load = float(state.get("_allostatic_load", 0.0) or 0.0)
    load = min(1.0, load + 0.02) if rd > 0.60 else max(0.0, load - 0.04)
    state["_allostatic_load"] = round(load, 4)
    # Mandatory recovery: high load overrides context and forces a low τ (rest).
    if load > 0.5:
        tau = min(tau, 0.12)
    # C4 smoothing (hysteresis): ease τ toward the target so it never jumps.
    prev = float(state.get("_resource_setpoint", tau) or tau)
    tau = round(0.7 * prev + 0.3 * max(0.10, min(0.45, tau)), 4)
    state["_resource_setpoint"] = tau
    return tau


def observe(fn: str, latency_ms: float, context: Dict[str, Any]) -> Dict[str, Any]:
    """Phase-0 convenience: record the measured cost, then assemble the would-be
    EVC and τ for telemetry/logging. No behavior change. Fail-safe."""
    out: Dict[str, Any] = {}
    try:
        predicted = predict_cost(fn, context)           # expectation BEFORE this act
        pe = record_cost(fn, latency_ms)                 # learn (EMA); pe = |actual−expected|
        nudge = 0.0
        # Phase 1 (C1): make the surprise FELT — signed, asymmetric, capped, flagged.
        if _affect_enabled() and isinstance(context, dict):
            signed = float(latency_ms) - predicted       # >0 costlier (strain), <0 cheaper (ease)
            raw = signed * (_NUDGE_GAIN_UP if signed > 0 else _NUDGE_GAIN_DOWN)
            nudge = max(-_NUDGE_CLAMP, min(_NUDGE_CLAMP, raw))
            try:
                from brain.cognition.dreaming.dream_cycle import dreaming_now
                if dreaming_now() and nudge > 0.0:
                    nudge = 0.0
            except Exception:
                pass
            if abs(nudge) >= _NUDGE_MIN:
                try:
                    from brain.affect.arbiter import submit_affect
                    submit_affect(context, "resource_deficit", nudge,
                                  weight=0.5, source="interoception:pe", ttl_cycles=3)
                except Exception:
                    nudge = 0.0
            else:
                nudge = 0.0
        _af = context.get("affect_state") or {}
        _rd = float(_af.get("resource_deficit", 0.0) or 0.0)
        out = {
            "fn": fn,
            "predicted_ms": round(predicted, 1),
            "actual_ms": round(float(latency_ms), 1),
            "pe_ms": pe,
            "deficit_nudge": round(nudge, 5),
            "would_be_evc": would_be_evc(fn, context),
            # Applied proactive-resource state (telemetry/UI):
            "resource_deficit": round(_rd, 3),
            "energy": round(max(0.0, min(1.0, 1.0 - _rd)), 3),     # energy = 1 − fatigue
            "tau_applied": round(float(_af.get("_resource_setpoint", setpoint_candidate(context)) or 0.15), 4),
            "tau_candidate": setpoint_candidate(context),
            "allostatic_load": round(float(_af.get("_allostatic_load", 0.0) or 0.0), 3),
        }
        context["_interoception"] = out
        log_private(
            f"[interoception] {fn}: pred={out['predicted_ms']}ms act={out['actual_ms']}ms "
            f"pe={out['pe_ms']}ms nudge={out['deficit_nudge']:+} evc={out['would_be_evc']} τ*={out['tau_candidate']}"
        )
    except Exception as exc:
        _log.warning("interoception.observe failed: %s", exc)
    return out
