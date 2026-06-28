"""Current-state readers for selection (Phase 4D, from select_function.py).

Tiny fail-safe readers of Orrin's persisted state that the selector and its
scoring helpers consult: the dominant core-emotion and the current focus-goal
name. Base-level — they read JSON state files only, with no dependency on the
selector's constants or scoring, so the upper layers can import them without a
cycle. Re-imported into select_function for its internal callers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

from brain.utils.json_utils import load_json
from brain.utils.goals import extract_current_focus_goal
from brain.utils.failure_counter import record_failure
from brain.paths import FOCUS_GOAL, SIGNAL_STATE_FILE, SELF_MODEL_FILE


def _dominant_signal() -> str:
    emo: Dict[str, Any] = load_json(SIGNAL_STATE_FILE, default_type=dict) or {}
    core = emo.get("core_signals", {})
    if isinstance(core, dict) and core:
        try:
            return str(max(core.items(), key=lambda kv: kv[1])[0])
        except Exception as _e:
            record_failure("select_function._dominant_signal", _e)
    return str(emo.get("dominant", "neutral"))


def _focus_goal_name() -> str:
    fg: Dict[str, Any] = load_json(FOCUS_GOAL, default_type=dict) or {}
    try:
        s = extract_current_focus_goal(fg)
        if s:
            return str(s)
    except Exception as _e:
        record_failure("select_function._focus_goal_name", _e)
    return str(fg.get("name", ""))


def _get_directive_text() -> str:
    sm: Dict[str, Any] = load_json(SELF_MODEL_FILE, default_type=dict) or {}
    cd = sm.get("core_directive")
    if isinstance(cd, dict):
        return str(cd.get("statement", "")) or ""
    if isinstance(cd, str):
        return cd
    return ""


def _get_focus_goal_text() -> str:
    fg: Dict[str, Any] = load_json(FOCUS_GOAL, default_type=dict) or {}
    try:
        s = extract_current_focus_goal(fg)
        if s:
            return str(s)
    except Exception as _e:
        record_failure("select_function._get_focus_goal_text", _e)
    name = str(fg.get("name", "") or "")
    desc = str(fg.get("description", "") or "")
    return (name + " " + desc).strip()


def _dominant_signal_and_stagnation_signal(context: Dict[str, Any] | None = None) -> Tuple[str, float]:
    # Prefer in-memory context so function selection uses the current cycle's
    # emotional state, not the stale disk file from the previous cycle.
    emo: Dict[str, Any]
    if context is not None:
        emo = context.get("affect_state") or {}
    else:
        emo = load_json(SIGNAL_STATE_FILE, default_type=dict) or {}
    core = emo.get("core_signals", {}) or {}
    stagnation_signal = float(core.get("stagnation_signal", emo.get("stagnation_signal", 0.0)) or 0.0)
    dom: str | None = None
    try:
        if isinstance(core, dict) and core:
            dom = str(max(core.items(), key=lambda kv: kv[1])[0])
    except Exception:
        dom = None
    return (dom or str(emo.get("dominant", "neutral"))), max(0.0, min(1.0, stagnation_signal))


def _recent_picks_from_ctx(ctx: Dict[str, Any]) -> List[str]:
    rp = ctx.get("recent_picks", [])
    return rp if isinstance(rp, list) else []
