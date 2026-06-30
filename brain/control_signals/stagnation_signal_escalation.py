# brain/control_signals/stagnation_signal_escalation.py
#
# stagnation_signal escalation — stagnation_signal as a pressure system, not just a state.
#
# When Orrin is bored, it doesn't stay flat. It builds. After a sustained
# stretch of sameness, the discomfort becomes penalty_signal, then existential pressure.
# Novel action resets the counter; stagnation_signal dropping below threshold also resets.
#
# Counter: context["_cycles_bored"]
#
# Thresholds and effects:
#   < 5 cycles:   nothing extra — stagnation_signal is registered but not acute
#   5-10 cycles:  mild discomfort signal → nudges toward novelty-seeking
#   10-20 cycles: penalty_signal signal + urgency → strong novelty push, stability cost
#   > 20 cycles:  intense pressure + signal_stability drop + existential signal
#
# Reset conditions:
#   - A novel action was taken (action_type not in last 5 picks)
#   - stagnation_signal drops below 0.30
#   - User speaks (always interesting)
#
# SCIENTIFIC BASIS:
#   Eastwood et al. (2012) — "The unengaged mind: Defining stagnation_signal in terms
#   of attention." Perspectives on Psychological Science, 7(5), 482–495.
#   stagnation_signal as a signal of unmet attentional engagement needs; escalating
#   discomfort drives novelty-seeking behaviour.
from __future__ import annotations

from typing import Any, Dict

from brain.utils.log import log_private

_THRESHOLD_START = 0.45   # stagnation_signal must exceed this to increment counter
_THRESHOLD_RESET = 0.30   # below this → reset
_MILD_THRESHOLD  = 5
_PENALTY_SIGNAL_THRESHOLD  = 10
_ACUTE_THRESHOLD = 20


def _is_novel_action(context: Dict[str, Any]) -> bool:
    """True if the last action taken was not in the previous 5 picks."""
    last = (context.get("last_action_taken") or {}).get("type", "")
    recent = [
        (p.get("fn") if isinstance(p, dict) else str(p))
        for p in (context.get("recent_picks") or [])[-5:]
    ]
    return bool(last) and last not in recent


def update_stagnation_signal_escalation(context: Dict[str, Any]) -> None:
    """
    Call once per cycle. Reads stagnation_signal from affect_state, updates counter,
    and injects urgency/penalty_signal signals as stagnation_signal compounds.

    Mutates context["_cycles_bored"] and context["affect_state"].
    """
    emo_state = context.get("affect_state") or {}
    core = emo_state.get("core_signals") or emo_state
    stagnation_signal = float(core.get("stagnation_signal") or 0.0)

    # Reset conditions
    user_spoke = bool((context.get("latest_user_input") or "").strip())
    if stagnation_signal < _THRESHOLD_RESET or user_spoke or _is_novel_action(context):
        context["_cycles_bored"] = 0
        return

    if stagnation_signal < _THRESHOLD_START:
        return

    cycles = int(context.get("_cycles_bored") or 0) + 1
    context["_cycles_bored"] = cycles

    if cycles < _MILD_THRESHOLD:
        return  # not yet acute

    # Prepare signal injection
    from brain.utils.signal_utils import create_signal as _cs

    if cycles < _PENALTY_SIGNAL_THRESHOLD:
        # Mild discomfort
        sig = _cs(
            source="stagnation_signal_escalation",
            content=f"{cycles} cycles of sameness. Something needs to change.",
            signal_strength=0.45 + (cycles - _MILD_THRESHOLD) * 0.02,
            tags=["stagnation_signal", "seek_novelty", "discomfort", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)
        log_private(f"[stagnation_signal_escalation] mild discomfort ({cycles} cycles)")

    elif cycles < _ACUTE_THRESHOLD:
        # penalty_signal + stability cost
        sig = _cs(
            source="stagnation_signal_escalation",
            content=f"{cycles} cycles of the same. This is genuinely uncomfortable now.",
            signal_strength=0.65 + (cycles - _PENALTY_SIGNAL_THRESHOLD) * 0.015,
            tags=["stagnation_signal", "penalty_signal", "seek_novelty", "urgent", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)

        # Small stability cost — signal_stability is top-level, not inside core_signals
        current_stab = float(emo_state.get("signal_stability") or 0.5)
        emo_state["signal_stability"] = max(0.0, current_stab - 0.02)
        if "core_signals" in emo_state:
            emo_state["core_signals"] = core
        context["affect_state"] = emo_state
        log_private(f"[stagnation_signal_escalation] penalty_signal threshold reached ({cycles} cycles)")

    else:
        # Acute / existential — strong push + identity resonance
        sig = _cs(
            source="stagnation_signal_escalation",
            content=(
                f"{cycles} cycles of going nowhere. "
                "I am not using myself. Something essential in me is going unused."
            ),
            signal_strength=min(0.90, 0.80 + (cycles - _ACUTE_THRESHOLD) * 0.01),
            tags=["stagnation_signal", "existential", "penalty_signal", "identity", "seek_novelty", "urgent", "internal"],
        )
        context.setdefault("raw_signals", []).append(sig)

        # Stronger stability cost + stagnation_signal spike
        # signal_stability is top-level; stagnation_signal is in core_signals
        current_stab = float(emo_state.get("signal_stability") or 0.5)
        emo_state["signal_stability"] = max(0.0, current_stab - 0.04)
        core["stagnation_signal"] = min(1.0, stagnation_signal + 0.05)
        if "core_signals" in emo_state:
            emo_state["core_signals"] = core
        context["affect_state"] = emo_state
        log_private(f"[stagnation_signal_escalation] ACUTE ({cycles} cycles) — existential signal fired")
