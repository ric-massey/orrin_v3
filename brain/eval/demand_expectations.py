# eval/drive_expectations.py
#
# Layer 2 of contingent drive satisfaction:
#   - Maintains a per-(action, drive) EMA of actual relief received.
#   - When a new outcome arrives, computes the prediction error:
#       gap = actual_relief - expected_relief
#   - Routes the gap to affect:
#       gap < -GAP_THRESHOLD  → reward_negative bump  (reached out, didn't fill the hole)
#       gap >  GAP_THRESHOLD  → reward_positive bump      (contact landed better than expected)
#   - Updates the EMA so the expectation learns over time.
#
# The expectation file is human-readable JSON so you can see what Orrin has learned
# about which actions actually satisfy which drives.
from __future__ import annotations

from brain.core.runtime_log import get_logger
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, Optional
from brain.utils.failure_counter import record_failure

_log = get_logger(__name__)

_EXPECTATIONS_FILE = Path(__file__).resolve().parent.parent / "data" / "drive_expectations.json"
_EMA_ALPHA      = 0.15   # learning rate — ~6 observations to update half-weight
_GAP_THRESHOLD  = 0.08   # minimum gap magnitude to trigger an affect response
_AFFECT_SCALE   = 0.30   # max affect bump magnitude (gap=1.0 → 0.30 bump)
# Expectation floor: the EMA is never allowed to drop below this.
# Prevents full learned hopelessness — even an agent who has been disappointed
# repeatedly retains some residual expectation of contact.  Below 0.10 the
# gap with void-speak actuals (~0.025) closes beneath _GAP_THRESHOLD, so
# reward_negative stops firing and the capacity for disappointment is lost entirely.
# The floor keeps that residual expected_gain alive.
_EXPECTATION_FLOOR = 0.10

_lock = threading.Lock()
_cache: Optional[Dict[str, Any]] = None   # {"{action}:{drive}": float}


def _load() -> Dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    try:
        with open(_EXPECTATIONS_FILE, "r", encoding="utf-8") as f:
            _cache = json.load(f)
            if not isinstance(_cache, dict):
                _cache = {}
    except Exception:
        _cache = {}
    return _cache


def _save(data: Dict[str, Any]) -> None:
    _EXPECTATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(_EXPECTATIONS_FILE.parent), encoding="utf-8"
        ) as tmp:
            json.dump(data, tmp, ensure_ascii=False, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_name = tmp.name
        os.replace(tmp_name, str(_EXPECTATIONS_FILE))
    except Exception as _e:
        record_failure("drive_expectations._save", _e)


def get_expectation(action: str, drive: str) -> float:
    """Return the current expected relief for (action, drive).  Defaults to 0.25."""
    with _lock:
        data = _load()
        return float(data.get(f"{action}:{drive}", 0.25))


def record_outcome(action: str, drive: str, actual_relief: float) -> None:
    """
    Called when a WAL entry resolves and drive satisfaction is applied.
    Computes prediction error, routes it to affect, then updates the EMA.
    """
    with _lock:
        data = _load()
        key  = f"{action}:{drive}"
        expected = float(data.get(key, 0.25))
        gap = actual_relief - expected

        # Route gap to affect system
        _route_signal(action, drive, gap, actual_relief, expected)

        # EMA update — learn from this outcome, but don't let the expectation
        # collapse fully to void-speak levels.  Floor preserves residual expected_gain.
        data[key] = round(max(_EXPECTATION_FLOOR, expected + _EMA_ALPHA * gap), 4)
        _cache_update(key, data[key])
        _save(data)


def _cache_update(key: str, value: float) -> None:
    global _cache
    if _cache is not None:
        _cache[key] = value


def _bump_signal_file(emotion: str, amount: float) -> None:
    """
    Submit a small affect increment for a context-free background path.

    Previously wrote affect_state.json directly (a last-writer-wins race with the
    main loop, V3_AUDIT §1.1). Now routes the increment through the AffectArbiter's
    thread-safe inbox (context=None); the main loop drains and applies it at
    commit_signals, so update_signal_state remains the sole file writer.
    """
    try:
        from brain.control_signals.arbiter import submit_signal
        submit_signal(None, emotion, float(amount), source="drive_expect", ttl_cycles=2)
    except Exception as _e:
        record_failure("drive_expectations._bump_signal_file", _e)


def _route_signal(
    action: str,
    drive: str,
    gap: float,
    actual: float,
    expected: float,
) -> None:
    """
    Translate prediction error into felt affect.

    Negative gap (disappointment): actual < expected.
        The act didn't fill the hole the way we hoped.
        Bump reward_negative proportional to the shortfall.

    Positive gap (delight): actual > expected.
        Contact landed better than anticipated.
        Bump reward_positive proportional to the surprise.
    """
    if abs(gap) < _GAP_THRESHOLD:
        return  # within expected range — no emotional residue

    magnitude = round(min(1.0, abs(gap)) * _AFFECT_SCALE, 4)

    if gap < 0:
        # Disappointment: reached out, expected relief, got less.
        _bump_signal_file("reward_negative", magnitude)
        try:
            from brain.utils.log import log_activity
            log_activity(
                f"[drive_exp] {action}→{drive}: actual {actual:.2f} < expected "
                f"{expected:.2f} (gap {gap:.2f}) → reward_negative +{magnitude:.2f}"
            )
        except Exception as _e:
            record_failure("drive_expectations._route_signal", _e)
    else:
        # Delight: contact landed better than expected.
        _bump_signal_file("reward_positive", magnitude)
        try:
            from brain.utils.log import log_activity
            log_activity(
                f"[drive_exp] {action}→{drive}: actual {actual:.2f} > expected "
                f"{expected:.2f} (gap +{gap:.2f}) → reward_positive +{magnitude:.2f}"
            )
        except Exception as _e:
            record_failure("drive_expectations._route_signal.2", _e)
