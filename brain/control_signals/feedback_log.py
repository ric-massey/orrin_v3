from __future__ import annotations
from brain.core.runtime_log import get_logger

from datetime import datetime, timezone
from typing import Any, Dict, List, Union
from pathlib import Path

from brain.utils.json_utils import load_json, save_json
from brain.control_signals.reward_signals.reward_signals import release_reward_signal
from brain.paths import (
    SIGNAL_STATE_FILE as _AFFECT_STATE_FILE,
    FEEDBACK_LOG_JSON as _FEEDBACK_LOG_JSON,
    REWARD_TRACE_JSON as _REWARD_TRACE_JSON,
)
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)

def _as_path(p: Union[str, Path]) -> Path:
    return p if isinstance(p, Path) else Path(p)

SIGNAL_STATE_FILE: Path = _as_path(_AFFECT_STATE_FILE)
FEEDBACK_LOG_JSON: Path = _as_path(_FEEDBACK_LOG_JSON)
REWARD_TRACE_JSON: Path = _as_path(_REWARD_TRACE_JSON)

# Context keys release_reward_signal actually reads (it uses the plain string
# keys "reward_trace"/"last_tags" — the old str(Path) keys never matched, so
# the trace it appended was silently overwritten by our stale copy below;
# DATA_FILE_AUDIT 2026-06-11 §7 map-drift sweep).
_LAST_TAGS = "last_tags"
_REWARD_TRACE = "reward_trace"

def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except (ValueError, TypeError):  # intentional: non-numeric → default
        return default

def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))

def log_feedback(
    goal: str,
    result: Union[str, Dict[str, Any]],
    emotion: str = "neutral",
    agent: str = "Orrin",
    score: Union[float, int, None] = None,
    file: Union[str, Path] = FEEDBACK_LOG_JSON,
) -> None:
    """
    Append a feedback entry and propagate a simple reward signal.

    - Persists to FEEDBACK_LOG_JSON.
    - Loads/saves emotional state and reward trace files.
    - Never raises: errors are swallowed to keep telemetry non-fatal.
    """
    try:
        now = datetime.now(timezone.utc).isoformat()

        # 1) Persist feedback entry
        entry = {
            "goal": str(goal),
            "result": result,
            "agent": str(agent),
            "emotion": str(emotion),
            "timestamp": now,
        }
        if score is not None:
            entry["score"] = _to_float(score)

        feedback_log: List[dict] = load_json(file, default_type=list)
        feedback_log.append(entry)
        save_json(file, feedback_log)

        # 2) Prepare reward context (in-memory structure)
        #    Use string keys (not Path objects) for robustness.
        affect_state = load_json(SIGNAL_STATE_FILE, default_type=dict)
        reward_trace = load_json(REWARD_TRACE_JSON, default_type=list)

        ctx: Dict[str, Any] = {
            "affect_state": affect_state,
            _REWARD_TRACE: reward_trace,
            _LAST_TAGS: [str(goal), str(agent)],
        }

        # 3) Decide reward channel & magnitude
        result_str = str(result).lower() if not isinstance(result, str) else result.lower()

        # If no explicit score, assign a reasonable default
        if score is None:
            if any(k in result_str for k in ("success", "helpful", "insightful", "effective")):
                actual = 0.8
            elif any(k in result_str for k in ("failure", "unhelpful", "useless", "error")):
                actual = 0.1
            else:
                actual = 0.4
        else:
            actual = _to_float(score, 0.0)

        actual = _clamp01(actual)
        expected = 0.6
        effort = 0.5

        if any(k in result_str for k in ("success", "helpful", "insightful", "effective", "ok", "done")):
            signal_type = "reward_signal"
            mode = "phasic"
        elif any(k in result_str for k in ("failure", "unhelpful", "useless", "error")):
            signal_type = "reward_signal"
            mode = "phasic"
        else:
            signal_type = "stability_signal"
            mode = "tonic"

        # 4) Emit reward signal; handle mutate-or-return styles
        new_ctx = release_reward_signal(
            ctx,
            signal_type=signal_type,
            actual_reward=actual,
            expected_reward=expected,
            effort=effort,
            mode=mode,
        ) or ctx  # in case the function mutates-in-place and returns None

        # 5) Persist reward trace only.
        # The affect_state here is a THROWAWAY disk snapshot (built at step 2), not
        # the live loop context — writing it back would overwrite concurrent
        # core_signal changes from the main loop (the last-writer-wins race in
        # V3_AUDIT §1.1). update_signal_state is the sole affect writer; the small
        # tonic nudge from this telemetry event is intentionally not persisted to
        # affect here. The reward trace is independent and safe to persist.
        save_json(REWARD_TRACE_JSON, new_ctx.get(_REWARD_TRACE, reward_trace))

    except Exception as _e:
        # Telemetry should never break the main flow
        record_failure("feedback_log.log_feedback", _e)
