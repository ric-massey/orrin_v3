# brain/cognition/state_awareness.py
#
# State → awareness: when a slow state becomes SALIENT, offer it to the Global
# Workspace so it can be noticed and acted on — the way a person mostly adapts
# to tiredness, time, or another's confusion without words, and consciously
# registers it only when it shifts or persists.
#
#   energy mode   — offered on a shift INTO active / rest / reactive (not while steady)
#   felt time     — offered on entering a later waiting phase (absence becomes felt)
#   theory of mind — a persistent misalignment (≥2 consecutive) is a binding item
#                    that joins the user's message (binding.py), so the situation
#                    "Ric said X — they don't feel understood" outranks the bare message
#
# The structured states already steer speech/selection every cycle; this only adds
# the salient-moment path. Symbolic throughout — no LLM reads any of it. Bias,
# never preempt (I7): offers compete; routing (selection/routing.py) is additive.
# Disable with ORRIN_STATE_AWARENESS=0.
from __future__ import annotations

import os
from typing import Any, Dict, Optional

from brain.utils.failure_counter import record_failure
from brain.utils.log import log_activity

TOM_RAN_KEY = "_tom_ran_this_cycle"   # transient; stripped from context.json (finalize)

_ENERGY_SHIFT: Dict[str, Dict[str, Any]] = {
    "rest":     {"content": "winding down — wanting to consolidate rather than reach", "salience": 0.50},
    "active":   {"content": "energy coming back — ready to reach further",             "salience": 0.50},
    "reactive": {"content": "on edge — wanting to keep things narrow and safe",        "salience": 0.55},
}

_WAITING_PHASE: Dict[str, Dict[str, Any]] = {
    "waiting_wondering":    {"content": "it's been a while since anyone was here",           "salience": 0.40},
    "waiting_settling":     {"content": "the quiet is settling in — no one has been here",    "salience": 0.45},
    "waiting_extended":     {"content": "a long stretch without contact now",                 "salience": 0.50},
    "waiting_long_absence": {"content": "it's been a very long time since contact",           "salience": 0.55},
}


def _enabled() -> bool:
    return os.environ.get("ORRIN_STATE_AWARENESS", "1") != "0"


# ── Theory of mind: once per cycle, as soon as the user's input is parsed ──────

def run_theory_of_mind(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Run ToM once per cycle. Called right after process_inputs (before binding
    and the fast Face reply, so both read THIS turn's read, not last turn's);
    think() calls it again as a no-op fallback."""
    if context.get(TOM_RAN_KEY):
        return context.get("theory_of_mind")
    context[TOM_RAN_KEY] = True
    try:
        from brain.cognition.theory_of_mind import simulate
        result = simulate(context)
        context["theory_of_mind"] = result
        context["_tom_text"] = (result or {}).get("surface_text", "")
        return result
    except Exception as e:
        record_failure("state_awareness.theory_of_mind", e)
        context["theory_of_mind"] = None
        context["_tom_text"] = ""
        return None


def tom_binding_item(context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The misalignment read as a binding item, or None. Only when a user spoke
    this cycle and ToM reports a persistent misalignment (its own ≥2 rule)."""
    if not _enabled():
        return None
    tom = context.get("theory_of_mind")
    if not isinstance(tom, dict) or not tom.get("misaligned"):
        return None
    if not (context.get("latest_user_input") or "").strip():
        return None
    n = int((tom.get("belief_model") or {}).get("consecutive_misalignments", 0) or 0)
    if n >= 3:
        content = f"{n} times now they don't feel understood — what I'm doing isn't landing"
        salience = 0.70
    else:
        content = "they corrected me again — they don't feel understood"
        salience = 0.60
    return {"content": content, "salience": salience, "consecutive": n}


# ── Energy + felt time: offered pre-think when they shift ─────────────────────

def offer_state_awareness(context: Dict[str, Any]) -> None:
    """Consume pending energy/felt-time shifts and offer the salient ones to the
    workspace. Consumes even when disabled, so a stale shift never fires later."""
    try:
        from brain.motivation.energy_orientation import consume_pending_shift
        shift = consume_pending_shift()
    except Exception as e:
        record_failure("state_awareness.energy", e)
        shift = None
    try:
        from brain.cognition.temporal_state import consume_pending_phase
        phase = consume_pending_phase()
    except Exception as e:
        record_failure("state_awareness.felt_time", e)
        phase = None
    if not _enabled():
        return
    try:
        from brain.cognition.global_workspace import offer_to_workspace
        to_mode = str((shift or {}).get("to") or "")
        if to_mode in _ENERGY_SHIFT:
            offer_to_workspace(context, {**_ENERGY_SHIFT[to_mode], "source": "energy", "kind": to_mode})
            log_activity(f"[awareness] offered energy shift {(shift or {}).get('from')}→{to_mode}")
        waiting = str((phase or {}).get("phase") or "")
        if waiting in _WAITING_PHASE:
            offer_to_workspace(context, {**_WAITING_PHASE[waiting], "source": "felt_time", "kind": waiting})
            log_activity(f"[awareness] offered felt-time phase {waiting}")
    except Exception as e:
        record_failure("state_awareness.offer", e)
