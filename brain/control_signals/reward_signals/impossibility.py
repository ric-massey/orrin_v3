# brain/control_signals/reward_signals/impossibility.py
#
# R10-8 — "reward must see impossibility."
#
# THE PROBLEM (Run 9 skeptic pass, item 10)
# `decide_to_write_code` was blocked at the LLM gate 369/369 times in one life
# and STILL held the #2 reward EMA (0.618). The reward path scored "the action
# ran without raising," not "an effect occurred." An action that can never
# succeed while a capability is absent (LLM circuit open, tool missing) kept
# looking attractive, so the selector kept picking it — burning cycles on a
# structurally impossible act.
#
# THE FIX (two seams)
#   1. account seam (finalize): while an action is impossible, its realized
#      reward is forced to zero-with-prejudice, so its EMA decays below the
#      selection default within one life.
#   2. selection seam (score_setup): while an action is impossible, it leaves
#      the selectable set entirely — with one periodic re-probe so a recovered
#      capability can re-enter.
#
# HOW A BLOCK IS DETECTED
# The loop marks the function it is about to dispatch (set_current_action);
# generate_response's tool-gate, on a "tool unavailable" denial, marks THAT
# function impossible (mark_from_gate). A function that actually runs to a
# real effect calls note_possible to clear itself. Structural, symbolic-safe:
# no LLM needed to decide impossibility — the gate's own refusal is the signal.
from __future__ import annotations

import threading
import time
from typing import Dict, Optional, Set

from brain.utils.json_utils import load_json, save_json
from brain.utils.failure_counter import record_failure
from brain.paths import DATA_DIR

_FILE = DATA_DIR / "action_impossibility.json"

# A block is believed for this long before the action gets ONE re-probe back
# into the selectable set. If the re-probe blocks again it is immediately
# re-marked; if it succeeds, note_possible clears it. Long enough that a dead
# API key doesn't get retried every few seconds, short enough that a recovered
# capability returns within a life.
_REPROBE_S = 900.0

# How many consecutive gate denials before an action is treated as impossible.
# One is enough — a single "tool unavailable" is already a structural block, not
# noise — but the counter is kept for observability (how wedged is it?).
_MIN_CONSECUTIVE = 1

_lock = threading.Lock()
_local = threading.local()


def set_current_action(name: Optional[str]) -> None:
    """The loop calls this around each cognitive-function dispatch so a gate
    denial inside the call can be attributed to the right action."""
    _local.action = str(name) if name else None


def clear_current_action() -> None:
    _local.action = None


def _current_action() -> Optional[str]:
    return getattr(_local, "action", None)


def _load() -> Dict[str, dict]:
    d = load_json(_FILE, default_type=dict) or {}
    return d if isinstance(d, dict) else {}


def _save(d: Dict[str, dict]) -> None:
    try:
        save_json(_FILE, d)
    except Exception as exc:
        record_failure("impossibility._save", exc)


def mark_impossible(action: str, reason: str) -> None:
    """Record that `action` was structurally blocked (gate refused it)."""
    if not action:
        return
    now = time.time()
    with _lock:
        d = _load()
        row = d.get(action) if isinstance(d.get(action), dict) else {}
        row = {
            "reason": str(reason)[:120],
            "ts": now,
            "consecutive": int(row.get("consecutive", 0)) + 1,
            "since": float(row.get("since", now)),
        }
        d[action] = row
        _save(d)


def mark_from_gate(reason: str) -> None:
    """Called from the LLM tool-gate's denial path. Attributes the block to the
    function the loop is currently dispatching, if any."""
    action = _current_action()
    if action:
        mark_impossible(action, reason)


def note_possible(action: str) -> None:
    """An action that actually ran to a real effect: clear any impossible mark."""
    if not action:
        return
    with _lock:
        d = _load()
        if action in d:
            del d[action]
            _save(d)


def is_impossible(action: str, now: Optional[float] = None) -> bool:
    """True while `action` is believed impossible — i.e. marked, at/above the
    consecutive floor, and not yet due for its periodic re-probe."""
    if not action:
        return False
    now = time.time() if now is None else now
    row = _load().get(action)
    if not isinstance(row, dict):
        return False
    if int(row.get("consecutive", 0)) < _MIN_CONSECUTIVE:
        return False
    # Due for a re-probe → let it back in for one attempt.
    if (now - float(row.get("ts", 0.0))) >= _REPROBE_S:
        return False
    return True


def impossible_actions(now: Optional[float] = None) -> Set[str]:
    """The set of actions currently outside the selectable set."""
    now = time.time() if now is None else now
    return {a for a in _load().keys() if is_impossible(a, now)}


def realized_reward_with_prejudice(act_key: str, actual_fb: float) -> float:
    """R10-8 account seam, extracted so it is provable by harness (F-LN8): an
    action the gate refused this cycle (LLM circuit open, tool absent) produced
    no effect no matter how cleanly it "ran" — pay it zero-with-prejudice so its
    EMA decays below the selection default instead of sitting high on the
    strength of not raising. Fail-safe: on any error the reward passes through."""
    try:
        if is_impossible(act_key):
            return 0.0
    except Exception as _ie:
        record_failure("finalize.finalize_cycle.impossible", _ie)
    return actual_fb
