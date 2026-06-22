"""Current-state readers for selection (Phase 4D, from select_function.py).

Tiny fail-safe readers of Orrin's persisted state that the selector and its
scoring helpers consult: the dominant core-emotion and the current focus-goal
name. Base-level — they read JSON state files only, with no dependency on the
selector's constants or scoring, so the upper layers can import them without a
cycle. Re-imported into select_function for its internal callers.
"""
from __future__ import annotations

from brain.utils.json_utils import load_json
from brain.utils.goals import extract_current_focus_goal
from brain.utils.failure_counter import record_failure
from brain.paths import FOCUS_GOAL, AFFECT_STATE_FILE


def _dominant_emotion() -> str:
    emo = load_json(AFFECT_STATE_FILE, default_type=dict) or {}
    core = emo.get("core_signals", {})
    if isinstance(core, dict) and core:
        try:
            return max(core.items(), key=lambda kv: kv[1])[0]
        except Exception as _e:
            record_failure("select_function._dominant_emotion", _e)
    return str(emo.get("dominant", "neutral"))


def _focus_goal_name() -> str:
    fg = load_json(FOCUS_GOAL, default_type=dict) or {}
    try:
        s = extract_current_focus_goal(fg)
        if s:
            return str(s)
    except Exception as _e:
        record_failure("select_function._focus_goal_name", _e)
    return str(fg.get("name", ""))
