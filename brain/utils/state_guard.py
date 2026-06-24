# utils/state_guard.py
"""
Proactive validator and sanitizer for Orrin's critical state files.

Addresses the null-crash pattern:
  float(state.get("key", default))  -- default only fires when key is ABSENT.
  If a key exists with a JSON null value, .get() returns None and float(None) crashes.

sanitize_all() coerces null/non-finite floats to safe defaults in-place so the
shape seen by all other code stays correct. Only fixes broken values; never adds
missing keys or changes structurally valid data.
"""
from __future__ import annotations
from brain.core.runtime_log import get_logger

import math
from pathlib import Path
from typing import Any, Dict, Tuple

from brain.utils.json_utils import load_json, save_json
from brain.utils.log import log_model_issue, log_activity
from brain.utils.failure_counter import record_failure
_log = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal coercion helpers
# ---------------------------------------------------------------------------

def _safe_float(val: Any, default: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Coerce val to a finite float in [lo, hi]; return default on None/NaN/inf."""
    try:
        v = float(val)
        if math.isfinite(v):
            return max(lo, min(hi, v))
    except (TypeError, ValueError) as _e:
        record_failure("state_guard._safe_float", _e)
    return default


def _safe_int(val: Any, default: int, lo: int = 0) -> int:
    try:
        v = int(val)
        return max(lo, v)
    except (TypeError, ValueError) as _e:
        record_failure("state_guard._safe_int", _e)
    return default


# ---------------------------------------------------------------------------
# Per-file sanitizers
# ---------------------------------------------------------------------------

# Emotions present in both the top-level affect_state and core_signals sub-dict.
_EMOTION_DEFAULTS: Dict[str, float] = {
    "positive_valence": 0.5, "negative_valence": 0.3, "exploration_drive": 0.6, "impasse_signal": 0.2,
    "confidence": 0.5, "motivation": 0.5, "stagnation_signal": 0.3, "expected_gain": 0.5,
    "threat_level": 0.2, "social_penalty": 0.1, "conflict_signal": 0.1, "penalty_signal": 0.0,
    "uncertainty": 0.3, "excitement": 0.3, "risk_estimate": 0.2, "stress": 0.2,
    "overwhelm": 0.1, "resource_deficit": 0.2,
}


def _fix_emotion_dict(d: Dict[str, Any]) -> bool:
    """Coerce null/non-finite emotion values in-place. Returns True if any fix applied."""
    changed = False
    for k, default in _EMOTION_DEFAULTS.items():
        if k in d and d[k] is not None:
            fixed = _safe_float(d[k], default)
            if fixed != d[k]:
                d[k] = fixed
                changed = True
        elif k in d and d[k] is None:
            d[k] = default
            changed = True
    return changed


def _sanitize_emotion_state(data: Any) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(data, dict):
        return {}, True

    changed = False

    # Fix top-level emotion keys (used directly by ORRIN_loop.py boot/cycle code)
    changed |= _fix_emotion_dict(data)

    # Fix nested core_signals sub-dict (used by emotion_utils, memory_io, etc.)
    core = data.get("core_signals")
    if isinstance(core, dict):
        changed |= _fix_emotion_dict(core)
    elif core is not None:
        # core_signals exists but is the wrong type — reset to empty dict
        data["core_signals"] = {}
        changed = True

    # Fix affect_stability (key may exist with null value)
    if "affect_stability" in data:
        stab = data["affect_stability"]
        fixed = _safe_float(stab, 1.0)
        if fixed != stab:
            data["affect_stability"] = fixed
            changed = True

    return data, changed


def _sanitize_cycle_count(data: Any) -> Tuple[Dict[str, Any], bool]:
    if isinstance(data, dict):
        c = data.get("count")
        if c is None or not isinstance(c, int) or isinstance(c, bool):
            data["count"] = _safe_int(c, 0)
            return data, True
        return data, False
    return {"count": 0}, True


def _sanitize_bandit_state(data: Any) -> Tuple[Dict[str, Any], bool]:
    if not isinstance(data, dict):
        return {}, True

    changed = False

    _FLOAT_FIELDS: Dict[str, Tuple[float, float, float]] = {
        "epsilon": (0.15, 0.0, 1.0),
        "gamma":   (0.9,  0.0, 1.0),
        "alpha":   (0.1,  0.0, 1.0),
        "beta":    (0.1,  0.0, 1.0),
        "lr":      (0.05, 0.0, 1.0),
    }
    for k, (default, lo, hi) in _FLOAT_FIELDS.items():
        if k in data:
            fixed = _safe_float(data[k], default, lo, hi)
            if fixed != data[k]:
                data[k] = fixed
                changed = True

    # t is an integer step counter
    if "t" in data:
        fixed_t = _safe_int(data["t"], 0)
        if fixed_t != data["t"]:
            data["t"] = fixed_t
            changed = True

    # Arm weights nested inside an "arms" dict
    arms = data.get("arms")
    if isinstance(arms, dict):
        for arm_data in arms.values():
            if not isinstance(arm_data, dict):
                continue
            for weight_key in ("weight", "value", "mu", "sigma", "alpha", "beta"):
                if weight_key in arm_data:
                    v = arm_data[weight_key]
                    if v is None or (isinstance(v, float) and not math.isfinite(v)):
                        arm_data[weight_key] = (
                            0.5 if weight_key in ("mu", "weight", "value") else 1.0
                        )
                        changed = True

    return data, changed


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def sanitize_all(paths_module=None) -> Dict[str, int]:
    """
    Load, validate, and re-save all critical state files.
    Returns {label: 1} for each file where fixes were applied. Empty dict = all clean.
    Safe to call at any time; never removes or adds keys, only fixes null/invalid values.
    """
    if paths_module is None:
        try:
            import brain.paths as paths_module
        except ImportError:  # intentional: paths module unavailable → {}
            return {}

    P = paths_module
    results: Dict[str, int] = {}

    _run(getattr(P, "AFFECT_STATE_FILE", None), "affect_state", _sanitize_emotion_state, results)
    _run(getattr(P, "CYCLE_COUNT_FILE",      None), "cycle_count",     _sanitize_cycle_count,   results)
    _run(getattr(P, "BANDIT_STATE_FILE",     None), "bandit_state",    _sanitize_bandit_state,  results)

    if results:
        log_activity(f"[state_guard] fixed {len(results)} file(s): {list(results.keys())}")
    return results


def _run(path, label: str, fn, results: Dict[str, int]) -> None:
    if path is None:
        return
    try:
        p = Path(path)
        if not p.exists():
            return
        data = load_json(p, default_type=dict)
        fixed_data, changed = fn(data)
        if changed:
            save_json(p, fixed_data)
            log_model_issue(f"[state_guard] sanitized {label}: null/invalid values coerced to safe defaults")
            results[label] = 1
    except Exception as e:
        log_model_issue(f"[state_guard] failed to sanitize {label}: {e}")
