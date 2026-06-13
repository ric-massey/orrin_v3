"""
think/consciousness_trigger.py

Evaluates whether Orrin should engage conscious (LLM-backed) processing
this cycle, or remain in silent unconscious-processing mode.

The loop already runs a rich unconscious layer every cycle:
  - affect state updates
  - embodiment reads (sensory, drives, social, body-sense)
  - signal injection (stagnation_signal, wonder, threads, tensions, values)
  - process_inputs() → top_signals

This trigger decides whether that silent layer's output warrants
deliberate reasoning.  Returns (True, reason) to fire conscious dispatch;
(False, "quiet") to let the cycle end silently.

Floor rule: never more than 5 consecutive silent cycles.  Prevents Orrin
from going fully dormant during extended quiet periods while still giving
genuine idle time between thoughts.
"""
from __future__ import annotations
from typing import Tuple

from utils.get_cycle_count import get_cycle_count


# ── Tuneable thresholds ───────────────────────────────────────────────────────
# Raise a threshold to make Orrin quieter on that signal.
# Lower it to make him more reactive.  The floor (MAX_SILENT_CYCLES) is the
# hard backstop — no matter what, he thinks at least once every N cycles.

_UNCERTAINTY_THRESHOLD   = 0.55   # core.uncertainty > this → think
_SIGNAL_STRENGTH_TRIGGER = 0.60   # any raw signal ≥ this → think
_EMOTION_SPIKE_DELTA     = 0.10   # affect spike > this in one cycle → think
_STAGNATION_SIGNAL_THRESHOLD       = 0.55   # stagnation_signal > this → think (needs stimulation)
_WONDER_THRESHOLD        = 0.50   # wonder > this → think (something interesting)
_ACTION_DEBT_TRIGGER     = 2      # cycles inactive on a committed goal → think
MAX_SILENT_CYCLES        = 3      # hard floor: think at least every N cycles


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
    goal    = context.get("committed_goal") or {}
    pre     = context.get("_emo_pre_cycle") or {}  # baseline snapshotted before pipeline

    # 1. User input — always engage when someone speaks
    if (context.get("latest_user_input") or "").strip():
        return True, "user_input"

    # 2. High uncertainty — genuine confusion or novelty needs deliberate reasoning
    uncertainty = float(core.get("uncertainty", 0) or 0)
    if uncertainty > _UNCERTAINTY_THRESHOLD:
        return True, f"high_uncertainty({uncertainty:.2f})"

    # 3. Strong inbound signal — drive pressure or environment demanding attention
    strong = [
        s for s in signals
        if isinstance(s, dict) and float(s.get("signal_strength", 0) or 0) >= _SIGNAL_STRENGTH_TRIGGER
    ]
    if strong:
        top = max(strong, key=lambda s: s.get("signal_strength", 0))
        return True, f"strong_signal({top.get('source','?')}@{top.get('signal_strength',0):.2f})"

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
    wonder = float(core.get("wonder", 0) or 0)
    if wonder > _WONDER_THRESHOLD:
        return True, f"wonder({wonder:.2f})"

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
