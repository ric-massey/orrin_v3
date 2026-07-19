# brain/control_signals/homeostasis.py
#
# HomeostasisManager — the single owner of *restoring forces* on affect.
#
# THE PROBLEM IT SOLVES (V3_AUDIT.md §3.2, D3/D8)
# Restoring/decay logic used to be scattered across at least six locations with
# independent rates and targets, and two of them disagreed on where a signal
# should rest (the now-deleted decay_affect_state pulled everything toward 0.5,
# while update_signal_state decays toward per-signal baselines). A homeostatic
# system cannot have two setpoints for one signal.
#
# This module centralises the restoring forces that act on core_signals each
# cycle:
#   1. apply_restoring_forces — exponential decay of every signal toward its
#      resting baseline (setpoints.CORE_BASELINES, the single source of truth),
#      plus the antagonist cross-inhibition pull that keeps impossible
#      co-saturations (e.g. impasse=1.0 AND confidence=1.0) from persisting.
#   2. enforce_velocity_budget — a hard cap on the NET L1 movement of the whole
#      core vector in one cycle, so that decay + buffer drain + triggers combined
#      can never lurch affect faster than a configured maximum (the "max emotional
#      velocity" the homeostatic model requires).
#
# Cannon (1932) homeostasis; Russell & Barrett (2000) core affect.
from __future__ import annotations

import os
from typing import Any, Dict, List

from brain.control_signals.setpoints import CORE_BASELINES, setpoint
from brain.utils.failure_counter import record_failure

# Antagonist pairs for sustained cross-inhibition. When a dominant signal is
# chronically elevated, its antagonists are pulled toward baseline faster than
# their natural decay — preventing impossible co-saturations.
ANTAGONISTS: Dict[str, List[str]] = {
    "reward_positive":  ["reward_negative", "low_affect_signal"],
    "reward_negative":  ["reward_positive", "expected_gain"],
    "conflict_signal":   ["affiliation_signal", "peace"],
    "threat_level":      ["confidence", "boldness"],
    "impasse_signal":    ["confidence", "motivation", "reward_positive"],
    "confidence":        ["threat_level", "uncertainty"],
    "motivation":        ["reward_negative", "stagnation_signal"],
    "exploration_drive": ["stagnation_signal"],
    "stagnation_signal": ["exploration_drive", "novelty_signal", "motivation"],
    "uncertainty":       ["confidence"],
}

_INHIBIT_THRESHOLD = 0.70
_INHIBIT_RATE = 0.04

# Default per-cycle net velocity cap on the core vector (L1). Tuned so a normal
# cycle (a few small nudges + gentle decay) passes untouched, but a cycle where
# many forces fire at once cannot move the whole vector more than this in total.
#
# Raised 1.20 → 1.80: at 1.20 a genuine multi-signal event (a real appraisal that
# legitimately moves valence + a drive + a couple of negatives at once) routinely
# pushed total L1 over the cap, so every delta got scaled DOWN proportionally and
# the would-be spike arrived as a ~0.02 nudge — drives never visibly moved. 1.80
# gives a coherent event the headroom to land a 0.1–0.3 excursion while still
# bounding a chaotic cycle where a dozen forces fire incoherently.
DEFAULT_MAX_L1 = 1.80


# ── Display homeostasis index — the single owner of "is he settled?" ──────────
# How close the WHOLE core vector sits to its resting setpoints: 1.0 = everything
# at rest, falling as signals deviate (agitation or saturation). This used to be
# computed inline inside the telemetry helper (ORRIN_loop._emit_signal), which
# meant the number the UI charted existed *only* in the translator — asking the
# brain "what is your homeostasis" gave a different answer than the chart
# (SPLIT_CONSCIOUSNESS_TELEMETRY_AUDIT_2026-06-19, F2). It now lives here, is
# written onto affect_state every cycle, and the emit helper merely reads it, so
# representations A (live state), B (disk) and C (telemetry) share one definition.
#
# exploration_drive legitimately rides high while exploring, so its deviation is
# down-weighted — a curious-but-otherwise-resting mind should still read settled.
_EXPLORATION_DEV_WEIGHT = 0.15
# Maps mean per-signal deviation onto the 0..1 index. At gain 1.6 a mean
# deviation of ~0.625 pins the index to 0 (fully agitated); typical resting
# deviation (~0.05) reads ~0.92 (clearly settled). Tuned so the index "breathes"
# across the normal operating band rather than saturating.
_HOMEOSTASIS_DEVIATION_GAIN = 1.6
_HOMEOSTASIS_DEFAULT = 0.8


def homeostasis_index(core: Dict[str, float]) -> float:
    """The 0..1 'is his whole affect vector near rest?' reading (1 = settled).

    Weighted mean absolute deviation of every numeric core signal from its
    resting setpoint, mapped through `_HOMEOSTASIS_DEVIATION_GAIN`. Fail-safe:
    returns `_HOMEOSTASIS_DEFAULT` if setpoints are unavailable or core is empty.
    """
    try:
        from brain.control_signals.setpoints import setpoint as _setpoint
    except ImportError:  # intentional: setpoints unavailable → fail-safe default
        return _HOMEOSTASIS_DEFAULT
    weighted_devs: List[tuple] = []
    for k, v in (core or {}).items():
        if not isinstance(v, (int, float)):
            continue
        weight = _EXPLORATION_DEV_WEIGHT if k == "exploration_drive" else 1.0
        weighted_devs.append((abs(float(v) - _setpoint(k)), weight))
    weight_total = sum(weight for _, weight in weighted_devs)
    if not weight_total:
        return _HOMEOSTASIS_DEFAULT
    mean_dev = sum(dev * weight for dev, weight in weighted_devs) / weight_total
    return max(0.0, min(1.0, 1.0 - mean_dev * _HOMEOSTASIS_DEVIATION_GAIN))


# NOTE (T0.1, Core-Architecture master plan 2026-06-25): the former
# `update_allostatic_load(state, core)` integrator was RETIRED here. It integrated
# *raw* exploration_drive deviation from baseline 0.25, saturated to 1.0 in ~540
# cycles and then pinned — so the top-level `allostatic_load` telemetry no longer
# tracked anything behaviourally active. The real, behaviourally-active allostatic
# variable is `_allostatic_load`, owned by interoception.allostatic_setpoint()
# (it accrues while running hot and forces recovery). Telemetry + the affect API
# now read THAT value; there is one allostatic integrator, not two.

# ── Homeostatic ceilings — the single source of truth ────────────────────────
# Per-signal soft maxima. Negative/conflicting signals cap lower than positive
# drives. update_signal_state claws any signal above its ceiling back down at
# CEILING_RATE per cycle. CRUCIAL: drive/reward *pumps* (cognitive_cost flow,
# temporal_pressure anticipation, prediction-error surprise) must also respect
# these via pump_signal() — when they capped at 1.0 instead, they out-ran the
# once-per-cycle clawback and pinned motivation/confidence/reward_positive near
# 0.95 with ~zero variance (the "manically content" flatline). One ceiling
# authority, enforced at every write site.
EMO_CEILINGS: Dict[str, float] = {
    "impasse_signal":   0.75,  # negative drive — cap hard so it can't dominate
    "uncertainty":      0.75,
    "conflict_signal":  0.65,
    "threat_level":     0.70,
    "reward_negative": 0.70,
    "social_deficit":   0.65,  # chronic but not acute — cap below hijack threshold
    "exploration_drive": 0.85,  # positive drives — allow higher peaks
    "motivation":       0.85,
    "confidence":       0.82,
    "reward_positive": 0.85,
    "expected_gain":    0.80,
    "novelty_signal":           0.85,
    "stagnation_signal": 0.80,
}
DEFAULT_CEILING = 0.85
CEILING_RATE    = 0.25   # fraction of excess removed per clawback call


def ceiling_for(name: str) -> float:
    """The homeostatic soft ceiling for a signal (DEFAULT_CEILING if unlisted)."""
    return EMO_CEILINGS.get(name, DEFAULT_CEILING)


def pump_signal(core: Dict[str, float], key: str, delta: float, *, default: float = 0.0) -> float:
    """
    Additively boost a core signal, but NEVER push it above its homeostatic
    ceiling. Demand/reward pumps must call this instead of `min(1.0, cur + delta)`:
    capping at 1.0 let pumps out-run the once-per-cycle ceiling clawback and pin
    the positive drives near saturation (the flatline). Mutates `core` in place
    and returns the new value.

    - Positive delta: result is capped at ceiling_for(key). If the signal is
      ALREADY at/over the ceiling (legacy overshoot), no boost is added — the
      clawback in update_signal_state owns bringing it back down at its own rate.
    - Non-positive delta: applied with a hard 0.0 floor (drains are never blocked).
    """
    cur = float(core.get(key, default) or default)
    if delta <= 0.0:
        core[key] = max(0.0, cur + delta)
        return core[key]
    ceiling = ceiling_for(key)
    if cur >= ceiling:
        return cur
    core[key] = min(ceiling, cur + delta)
    return core[key]


def apply_restoring_forces(
    state: Dict,
    core: Dict[str, float],
    *,
    decay_rate: float,
    hours_passed: float,
) -> None:
    """
    Apply the single decay law (toward CORE_BASELINES) plus antagonist
    cross-inhibition to `core` in place.

    Mirrors the exact numeric behaviour previously inlined in
    update_signal_state, now owned here so there is one restoring-force authority.
    Honours state["emotional_decay"] (default True) for the baseline decay.

    ALLOSTASIS NOTE (Grounded Cognition plan, Phase 1B / invariant #1): this decays
    toward a FIXED baseline on purpose — it is NOT forced return-to-zero, and the
    setpoint is deliberately not value-tracking. Allostasis (a standing condition
    holding a signal elevated) is emergent: a genuine problem is re-driven by fresh
    appraisal every cycle, so drive-vs-decay settles at an elevated EQUILIBRIUM,
    while a one-off spike with no re-drive decays back to baseline. A value-tracking
    setpoint would create positive feedback (high signal → high setpoint → less
    decay → saturation) — the very runaway the appraisal-saturation fix removed.
    The one signal with an explicit shifting setpoint is resource_deficit
    (cost_prediction.allostatic_setpoint), where mandatory recovery is needed and a
    bounded load integrator prevents the runaway. See
    tests/brain/test_homeostasis.py::test_standing_pressure_holds_signal_elevated_but_spike_decays.
    """
    # ── 1. Baseline decay: exponential approach to each signal's resting value ──
    if state.get("emotional_decay", True):
        for emo, val in list(core.items()):
            val_f = float(val) if isinstance(val, (int, float)) else CORE_BASELINES.get(emo, 0.0)
            target = CORE_BASELINES.get(emo, 0.0)
            neutral_pull = target - val_f
            core[emo] = max(0.0, min(1.0, val_f + neutral_pull * (1 - pow(1 - decay_rate, hours_passed))))


# ── B3 / P5: time-at-ceiling accelerator on the per-call restoring pull ───────
# Diagnosis (B3_DECAY_DIAGNOSIS_2026-07-01.md): the 2026-07-01 run confirmed the
# drives themselves pin (~0.84 all life) — pump rate beats the flat per-call decay
# rate, so the restoring pull settles at an elevated equilibrium and never breaks
# it. Per the plan ("tune the existing law, do not add a second one"), this does
# NOT add a new decay law: it scales the EXISTING per-call restoring rate up the
# longer a signal has sat pinned far above its setpoint, so chronic saturation
# relaxes while a fresh acute spike still decays at the base rate (urgency and
# the survival floor are untouched — a spike has streak 0). Opponent-process
# habituation: repeated/sustained stimulation strengthens the b-process
# (Solomon & Corbit 1974) — the counter-force GROWS with time-at-ceiling.
#
# Tunables (env-overridable so the ablation panel / experiments can move them
# without code edits; P7 reads the same knobs):
#   ORRIN_SIGNAL_DECAY      — master switch for the per-call restoring pull
#                             (default on; off reproduces "hot and flat" for A/B)
#   ORRIN_PIN_MARGIN        — how far above setpoint counts as "pinned"
#   ORRIN_PIN_ACCEL_WINDOW  — calls-at-pin for the multiplier to grow by 1×
#   ORRIN_PIN_ACCEL_MAX     — cap on the multiplier
def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


PIN_MARGIN       = _env_float("ORRIN_PIN_MARGIN", 0.20)
PIN_ACCEL_WINDOW = max(1.0, _env_float("ORRIN_PIN_ACCEL_WINDOW", 40.0))
PIN_ACCEL_MAX    = max(1.0, _env_float("ORRIN_PIN_ACCEL_MAX", 4.0))
_PIN_STREAK_KEY  = "_pin_streaks"


def signal_decay_enabled() -> bool:
    """Master switch for the per-call restoring pull (ablation knob, default on)."""
    return str(os.environ.get("ORRIN_SIGNAL_DECAY", "1")).strip().lower() not in (
        "0", "false", "no", "off")


def update_pin_streaks(state: Dict[str, Any], core: Dict[str, float]) -> Dict[str, int]:
    """Advance the per-signal time-at-ceiling counters (call ONCE per cycle).

    A signal counts as pinned while it sits more than PIN_MARGIN above its
    resolved setpoint. Dropping back below the margin clears its streak — so the
    accelerator releases as soon as the signal actually relaxes, giving
    rise-and-relax rather than a one-way clamp. Streaks persist in `state` (the
    affect-state file) so a pin that spans process restarts still accelerates.
    """
    streaks = state.get(_PIN_STREAK_KEY)
    if not isinstance(streaks, dict):
        streaks = {}
        state[_PIN_STREAK_KEY] = streaks
    for key, val in list(core.items()):
        if not isinstance(val, (int, float)):
            continue
        if float(val) - setpoint(key) > PIN_MARGIN:
            streaks[key] = int(streaks.get(key, 0)) + 1
        elif key in streaks:
            del streaks[key]
    return streaks


def pin_multiplier(state: Dict[str, Any], key: str) -> float:
    """Read-only accelerator on the per-call restoring rate: 1.0 for a fresh
    spike, growing linearly with time-at-ceiling to PIN_ACCEL_MAX."""
    streaks = state.get(_PIN_STREAK_KEY)
    n = int(streaks.get(key, 0)) if isinstance(streaks, dict) else 0
    return 1.0 + min(PIN_ACCEL_MAX - 1.0, n / PIN_ACCEL_WINDOW)


# ── R10-9: hard-bound saturation tripwire ────────────────────────────────────
# The pin-streak accelerator above relaxes a signal sitting ABOVE its setpoint.
# It does not catch the pathology Run 9 hit: a signal welded to a HARD BOUND
# (drive_mastery == 1.00 all life) whose pump beats even the max accelerator, so
# the ignition threshold it feeds never discriminated once — and nobody noticed
# for ≥1 run because ignition stopped being scored after Run 3. Same family as
# the frozen-distress attractor found earlier: when the normal restoring law has
# demonstrably failed for hundreds of cycles, break the attractor decisively and
# say so loudly. This is a safety net, not a second decay law — it only fires
# after SATURATION_MAX_CYCLES at a bound, which healthy dynamics never reach.
SATURATION_MAX_CYCLES = int(_env_float("ORRIN_SATURATION_MAX_CYCLES", 500.0))
_SATURATION_EPS       = _env_float("ORRIN_SATURATION_EPS", 0.005)
# A bound is only pathological when it is FAR from where the signal should rest.
# Most negative/threat signals (threat_level, loss_signal, conflict_signal, …)
# have setpoint 0.0 — sitting at 0.0 is correct rest, not saturation. Only a
# signal welded at a bound at least this far from its setpoint (e.g. drive_mastery
# at 1.0, setpoint 0.0) is the frozen-attractor pathology this tripwire targets.
# Without this guard the tripwire manufactures fake affect: it kicks a correctly-
# resting loss_signal/rejection_signal off 0.0 every 500 cycles.
_SATURATION_MARGIN    = _env_float("ORRIN_SATURATION_MARGIN", 0.30)
# F-LN5 (Run 10 verdict delta 3): the consecutive-streak arm is WOBBLE-BLIND —
# drive_mastery spent ~all of Run 10 welded at 1.00 but its brief dips
# (0.84–0.96) reset the streak every time, so a 500-consecutive trip never
# fired. Second arm: a signal at a far-from-setpoint bound for at least this
# FRACTION of a full SATURATION_MAX_CYCLES window trips regardless of dips.
_SATURATION_FRACTION  = _env_float("ORRIN_SATURATION_FRACTION", 0.95)
_SAT_STREAK_KEY       = "_saturation_streaks"
_SAT_WINDOW_KEY       = "_saturation_windows"


def _break_attractor(signals: Dict[str, float], key: str, v: float, n: int,
                     cycle: int, arm: str) -> None:
    """Kick a welded signal decisively off its bound toward the setpoint (not all
    the way: enough to re-enter the discriminating band and let normal dynamics
    take over), with the loud [saturation] log + telemetry event."""
    target = setpoint(key)
    bound = 1.0 if v >= 0.5 else 0.0
    recal = bound + (target - bound) * 0.5
    signals[key] = max(0.0, min(1.0, recal))
    try:
        from brain.core.runtime_log import get_logger
        get_logger(__name__).warning(
            "[saturation] %s welded at %.3f for %d cycles (%s) — forced "
            "recalibration to %.3f (setpoint %.3f) at cycle %d",
            key, v, n, arm, signals[key], target, cycle)
    except Exception as _le:
        record_failure("homeostasis.saturation_tripwire.log", _le)
    try:
        from brain.events import record_event as _rec
        _rec({"type": "saturation", "signal": key, "stuck_value": round(v, 4),
              "cycles": n, "arm": arm,
              "recalibrated_to": round(signals[key], 4), "cycle": cycle})
    except Exception as _re:
        record_failure("homeostasis.saturation_tripwire.event", _re)


def saturation_tripwire(state: Dict[str, Any], signals: Dict[str, float],
                        cycle: int = 0) -> List[str]:
    """Advance per-signal time-at-BOUND counters and, when one crosses the trip
    condition, forcibly recalibrate that signal toward its setpoint, reset its
    counters, and emit a loud [saturation] log + telemetry event. Two arms:
      • streak — SATURATION_MAX_CYCLES consecutive cycles at a bound (fast path);
      • fraction (F-LN5) — ≥ _SATURATION_FRACTION of a SATURATION_MAX_CYCLES
        tumbling window at a bound, which catches the wobble pattern the streak
        provably misses (Run 10's drive_mastery: welded with periodic dips).
    Mutates `signals` in place. Returns the list of signals recalibrated this
    call (usually empty). Call ONCE per cycle."""
    streaks = state.get(_SAT_STREAK_KEY)
    if not isinstance(streaks, dict):
        streaks = {}
        state[_SAT_STREAK_KEY] = streaks
    windows = state.get(_SAT_WINDOW_KEY)
    if not isinstance(windows, dict):
        windows = {}
        state[_SAT_WINDOW_KEY] = windows

    fired: List[str] = []
    for key, val in list(signals.items()):
        if not isinstance(val, (int, float)):
            continue
        v = float(val)
        at_bound = (v <= _SATURATION_EPS) or (v >= 1.0 - _SATURATION_EPS)
        # A bound that IS (near) the signal's healthy setpoint is correct rest,
        # not a frozen attractor — only a bound far from setpoint is pathological.
        if at_bound and abs(v - setpoint(key)) <= _SATURATION_MARGIN:
            at_bound = False

        # Fraction arm (F-LN5). Tumbling window: count bound-hits over each full
        # SATURATION_MAX_CYCLES block; a dip costs one hit instead of resetting
        # the whole clock. Only near-bound values weld — track the last bound-side
        # value seen so the kick direction is the bound's, not a dip's.
        w = windows.get(key)
        if not isinstance(w, dict):
            w = {"n": 0, "hits": 0, "last_bound_v": v}
            windows[key] = w
        w["n"] = int(w.get("n", 0)) + 1
        if at_bound:
            w["hits"] = int(w.get("hits", 0)) + 1
            w["last_bound_v"] = v
        window_full = w["n"] >= SATURATION_MAX_CYCLES
        frac_trip = window_full and (w["hits"] / max(1, w["n"])) >= _SATURATION_FRACTION
        if window_full and not frac_trip:
            windows[key] = {"n": 0, "hits": 0, "last_bound_v": v}

        if not at_bound:
            if key in streaks:
                del streaks[key]
            if frac_trip:
                _break_attractor(signals, key, float(w.get("last_bound_v", v)),
                                 int(w["n"]), cycle, arm="fraction")
                windows[key] = {"n": 0, "hits": 0, "last_bound_v": v}
                streaks[key] = 0
                fired.append(key)
            continue

        n = int(streaks.get(key, 0)) + 1
        streaks[key] = n
        if n < SATURATION_MAX_CYCLES and not frac_trip:
            continue
        _break_attractor(signals, key, v, n if n >= SATURATION_MAX_CYCLES else int(w["n"]),
                         cycle, arm="streak" if n >= SATURATION_MAX_CYCLES else "fraction")
        streaks[key] = 0
        windows[key] = {"n": 0, "hits": 0, "last_bound_v": v}
        fired.append(key)
    return fired


def apply_cross_inhibition(core: Dict[str, float]) -> None:
    """
    Sustained cross-inhibition: when a dominant signal exceeds the inhibition
    threshold, pull its antagonists toward baseline, amplified by the excess.
    Prevents impossible co-saturations persisting cycle after cycle.
    """
    for emo, opps in ANTAGONISTS.items():
        val = float(core.get(emo, 0.0))
        if val > _INHIBIT_THRESHOLD:
            excess = val - _INHIBIT_THRESHOLD
            for opp in opps:
                if opp in core:
                    opp_val = float(core[opp])
                    base = CORE_BASELINES.get(opp, 0.0)
                    pull = base - opp_val
                    core[opp] = max(base, opp_val + pull * _INHIBIT_RATE * (excess / 0.1))


def enforce_velocity_budget(
    core: Dict[str, float],
    prev_core: Dict[str, float],
    *,
    max_l1: float = DEFAULT_MAX_L1,
) -> float:
    """
    Cap the NET per-cycle L1 movement of the core vector relative to its
    cycle-start snapshot. If the summed absolute change across all signals exceeds
    max_l1, scale every signal's delta down proportionally so the total movement
    equals max_l1. Returns the pre-clamp total L1 movement (for telemetry).

    This is the single mathematical "max emotional velocity" cap the homeostatic
    model requires — it bounds the combined effect of decay + buffer drain +
    triggers + appraisal that all mutate core within one update cycle.
    """
    if not isinstance(prev_core, dict) or not prev_core:
        return 0.0

    deltas: Dict[str, float] = {}
    total = 0.0
    for k, v in core.items():
        try:
            cur = float(v)
        except (TypeError, ValueError):
            continue
        if k not in prev_core:
            continue
        try:
            prev = float(prev_core[k])
        except (TypeError, ValueError):
            continue
        d = cur - prev
        if d:
            deltas[k] = d
            total += abs(d)

    if total <= max_l1 or total <= 0.0:
        return total

    scale = max_l1 / total
    for k, d in deltas.items():
        prev = float(prev_core[k])
        core[k] = max(0.0, min(1.0, prev + d * scale))
    return total
