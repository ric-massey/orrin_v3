"""
think/deliberation_gate.py

Decides whether to dispatch expensive deliberate (LLM-backed) reasoning this
cycle, or stay in the cheap background-processing mode.

The loop already runs a rich background layer every cycle:
  - control-signal state updates
  - host-state reads (sensory, drives, social, body-sense)
  - signal injection (stagnation_signal, wonder, threads, tensions, values)
  - process_inputs() → top_signals

This gate decides whether that background layer's output warrants deliberate
reasoning.  Returns (True, reason) to dispatch deliberation; (False, "quiet")
to let the cycle end silently.

Floor rule: never more than 5 consecutive silent cycles.  Prevents the runtime
from going fully dormant during extended quiet periods while still giving
genuine idle time between dispatches.
"""
from __future__ import annotations
from brain.cognition.global_workspace import bound_goal
from collections import deque
import os
from typing import Tuple

from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.log import log_activity


# ── Tuneable thresholds ───────────────────────────────────────────────────────
# Raise a threshold to make Orrin quieter on that signal.
# Lower it to make him more reactive.  The floor (MAX_SILENT_CYCLES) is the
# hard backstop — no matter what, he thinks at least once every N cycles.

_UNCERTAINTY_THRESHOLD   = 0.55   # core.uncertainty > this → think
_SIGNAL_STRENGTH_TRIGGER = 0.60   # trigger-3 constant (cold-start / flag-off value)
_EMOTION_SPIKE_DELTA     = 0.10   # affect spike > this in one cycle → think
_STAGNATION_SIGNAL_THRESHOLD       = 0.55   # stagnation_signal > this → think (needs stimulation)
_WONDER_THRESHOLD        = 0.50   # wonder > this → think (something interesting)
_ACTION_DEBT_TRIGGER     = 2      # cycles inactive on a committed goal → think
MAX_SILENT_CYCLES        = 3      # hard floor: think at least every N cycles
                                  # (liveness insurance — NOT behavior shaping;
                                  # stays under the Run 11 de-clamp audit §6.3)

# ── C1 (Run 11 §6.1): ignition threshold → adaptive statistic ─────────────────
# Run 10 ignited on 98.8 % of cycles: with a CONSTANT 0.60 line, a signal
# economy that mostly runs hot ignites almost always — the constant does a
# distribution's job. The trigger-3 line becomes a rolling PERCENTILE of the
# actual effective-strength distribution (post-habituation, per-cycle max), so
# "strong" means strong RELATIVE TO RECENT LIFE. A pinned signal cannot
# saturate a percentile gate: its own value IS the percentile, and the adaptive
# comparison is strictly-greater. B1 sameness-habituation stays as the
# antagonist; MAX_SILENT_CYCLES stays as the liveness floor. Flag exists for
# post-hoc bisection, ON for Run 11.
_ADAPTIVE_IGNITION   = os.environ.get("ORRIN_ADAPTIVE_IGNITION", "1") != "0"
_IGNITION_PCTL       = float(os.environ.get("ORRIN_IGNITION_PCTL", "80.0"))
_EFF_HISTORY_WINDOW  = 200   # rolling window of per-cycle max effective strengths
_PCTL_MIN_SAMPLES    = 30    # constant line until the distribution is warm
_THR_FLOOR, _THR_CEIL = 0.30, 0.95   # sanity band on the adaptive line


def _eff_history(context: dict) -> "deque":
    hist = context.get("_ignition_eff_history")
    if not isinstance(hist, deque):
        hist = deque(maxlen=_EFF_HISTORY_WINDOW)
        context["_ignition_eff_history"] = hist
    return hist


def signal_trigger_threshold(context: dict) -> float:
    """The trigger-3 line this cycle: the rolling percentile of observed
    effective strengths (C1), or the legacy constant when the flag is off or
    the distribution is cold."""
    if not _ADAPTIVE_IGNITION:
        return _SIGNAL_STRENGTH_TRIGGER
    hist = _eff_history(context)
    if len(hist) < _PCTL_MIN_SAMPLES:
        return _SIGNAL_STRENGTH_TRIGGER
    vals = sorted(hist)
    idx = min(len(vals) - 1, max(0, int(round((_IGNITION_PCTL / 100.0) * (len(vals) - 1)))))
    return max(_THR_FLOOR, min(_THR_CEIL, float(vals[idx])))

# ── B1 ignition habituation (RUN4_FIX_PLAN §B1 — the jammed-horn law) ──────────
# Trigger 3 fires on any raw signal ≥ 0.60 and short-circuits every lower trigger,
# so an unchanged social_presence@1.00 (or action_debt, or drive_rest — three
# lives, three horns) won ignition every cycle forever and starved emotion /
# prediction-error / consolidation. Habituation attenuates a signal that keeps
# firing at the SAME (source, quantized-value) key: eff = raw / (1 + k·n_identical).
# The instant the value changes the key changes and full strength returns — this
# habituates to SAMENESS, not to the source. One mechanism at the gate, not a
# fourth per-drive patch.
_IGNITION_WINDOW      = 50    # M: how many recent trigger-3 wins to remember
_HABITUATION_K        = 0.25  # a key that won 12 of the last 50 → ×0.25


def _ignition_window(context: dict) -> "deque":
    win = context.get("_ignition_recent")
    if not isinstance(win, deque):
        win = deque(maxlen=_IGNITION_WINDOW)
        context["_ignition_recent"] = win
    return win


def _sig_key(source, strength) -> tuple:
    """The habituation identity of a signal: its source + coarsely-quantized
    strength. A changed value ⇒ changed key ⇒ full strength returns."""
    return (str(source or "?"), round(float(strength or 0.0), 1))


# ── Trigger evaluation ────────────────────────────────────────────────────────

def should_think(context: dict) -> Tuple[bool, str]:
    """
    Returns (fire: bool, reason: str).

    Checks triggers in priority order.  The first match short-circuits.
    Logging the reason lets the activity log show why each cycle fired or not.
    """
    emo     = context.get("affect_state") or {}
    core    = emo.get("core_signals") if isinstance(emo.get("core_signals"), dict) else emo
    signals = context.get("raw_signals") or []
    goal    = bound_goal(context) or {}
    pre     = context.get("_emo_pre_cycle") or {}  # baseline snapshotted before pipeline

    # 1. User input — always engage when someone speaks
    if (context.get("latest_user_input") or "").strip():
        return True, "user_input"

    # 2. High uncertainty — genuine confusion or novelty needs deliberate reasoning
    uncertainty = float(core.get("uncertainty", 0) or 0)
    if uncertainty > _UNCERTAINTY_THRESHOLD:
        return True, f"high_uncertainty({uncertainty:.2f})"

    # 3. Strong inbound signal — drive pressure or environment demanding attention.
    # B1: rank by EFFECTIVE strength (raw attenuated by how often this exact
    # (source, quantized value) key has already won recently), so a jammed horn
    # demotes below the 0.60 line and the gate FALLS THROUGH to triggers 4–14,
    # restoring the emotion / prediction-check / consolidation diet.
    win = _ignition_window(context)
    thr = signal_trigger_threshold(context)   # C1: distribution-derived line
    strong = []
    max_eff = 0.0
    for s in signals:
        if not isinstance(s, dict):
            continue
        raw = float(s.get("signal_strength", 0) or 0)
        if raw <= 0.0:
            continue
        key = _sig_key(s.get("source"), raw)
        n_identical = sum(1 for k in win if k == key)
        eff = raw / (1.0 + _HABITUATION_K * n_identical)
        max_eff = max(max_eff, eff)
        # Once the percentile is live, compare STRICTLY greater: a pinned
        # signal equals its own percentile and can never win on pinnedness
        # alone. Cold-start / flag-off keeps the legacy ≥ against the constant.
        _adaptive_live = (_ADAPTIVE_IGNITION
                          and len(_eff_history(context)) >= _PCTL_MIN_SAMPLES)
        passed = (eff > thr) if _adaptive_live else (eff >= thr)
        if passed:
            strong.append((s, raw, eff, key))
    # C1: the distribution learns from every cycle (quiet ones included) so the
    # line tracks what "strong" means in THIS stretch of life.
    _eff_history(context).append(round(max_eff, 4))
    if strong:
        s, raw, eff, key = max(strong, key=lambda t: t[2])
        win.append(key)   # append only on a genuine trigger-3 win (plan §B1)
        src = s.get("source", "?")
        if eff < raw - 1e-6:
            log_activity(f"[deliberation_gate] strong_signal_habituated "
                         f"({src}@{raw:.2f}→eff {eff:.2f}) still fired")
        return True, f"strong_signal({src}@{raw:.2f})"
    # A raw-strong signal that got habituated BELOW the line does NOT short-circuit
    # — the gate falls through to triggers 4–14 (the restored emotion/prediction
    # diet). Recovery is by value change, not window aging: a changed value is a
    # new key with a zero streak, so full strength returns immediately.
    _habituated = [s for s in signals if isinstance(s, dict)
                   and float(s.get("signal_strength", 0) or 0) >= thr]
    if _habituated:
        _top = max(_habituated, key=lambda s: s.get("signal_strength", 0))
        log_activity(f"[deliberation_gate] strong_signal_habituated "
                     f"({_top.get('source','?')}@{float(_top.get('signal_strength',0) or 0):.2f}) "
                     f"demoted — falling through to lower triggers")

    # 4. Sudden negative affective spike — distress that warrants processing
    for emotion in ("impasse_signal", "threat_level", "conflict_signal", "social_penalty", "loss_signal"):
        now_val = float(core.get(emotion, 0) or 0)
        pre_val = float(pre.get(emotion, 0) or 0)
        if now_val - pre_val > _EMOTION_SPIKE_DELTA:
            return True, f"emotion_spike_{emotion}(+{now_val - pre_val:.2f})"

    # 5. Prediction error flagged — something unexpected happened
    if context.get("_prediction_error"):
        return True, "prediction_error"

    # 6. Active goal is off-track — needs replanning
    if goal.get("_drift_detected") or goal.get("_stalled"):
        return True, "goal_drift_or_stall"

    # 7. Action debt — any committed goal stalled for too long
    active_goals = context.get("committed_goals") or ([goal] if goal else [])
    debt = int(context.get("action_debt", 0) or 0)
    if active_goals and debt >= _ACTION_DEBT_TRIGGER:
        return True, f"action_debt({debt})"

    # 8. Multiple active goals — juggling commitments warrants deliberate attention
    if len(active_goals) >= 2:
        return True, f"multi_goal({len(active_goals)}_active)"

    # 9. stagnation_signal — seeking stimulation, nothing to do in passive mode
    stagnation_signal = float(core.get("stagnation_signal", 0) or 0)
    if stagnation_signal > _STAGNATION_SIGNAL_THRESHOLD:
        return True, f"stagnation_signal({stagnation_signal:.2f})"

    # 10. Wonder is elevated — something genuinely interesting to sit with
    wonder = float(core.get("novelty_signal", 0) or 0)
    if wonder > _WONDER_THRESHOLD:
        return True, f"novelty_signal({wonder:.2f})"

    # 11. exploration_drive spike — positive engagement demand
    exploration_drive     = float(core.get("exploration_drive", 0) or 0)
    pre_exploration_drive = float(pre.get("exploration_drive", 0) or 0)
    if exploration_drive - pre_exploration_drive > _EMOTION_SPIKE_DELTA:
        return True, f"exploration_drive_spike(+{exploration_drive - pre_exploration_drive:.2f})"

    # 12. Motivation spike — surge of drive worth acting on
    motivation     = float(core.get("motivation", 0) or 0)
    pre_motivation = float(pre.get("motivation", 0) or 0)
    if motivation - pre_motivation > 0.16:
        return True, f"motivation_spike(+{motivation - pre_motivation:.2f})"

    # 13. High exploration_drive + any active goal — engaged mind with something to work on
    if exploration_drive > 0.65 and active_goals:
        return True, f"curious_with_goals({exploration_drive:.2f})"

    # 14. Periodic floor — never stay silent more than MAX_SILENT_CYCLES cycles
    current_cycle = get_cycle_count()
    last_think    = int(context.get("_last_think_cycle", 0) or 0)
    silent_run    = current_cycle - last_think
    if silent_run >= MAX_SILENT_CYCLES:
        return True, f"periodic_floor(silent_for={silent_run})"

    return False, "quiet"
