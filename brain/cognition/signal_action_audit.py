"""Signal→action follow-through audit — SIGNAL_TO_ACTION_AUDIT_2026-06-18 §1.4 / R1.

Closes the observability gap the audit names: `behavior_changes.json` records that
a corrective was *armed*, never whether it *landed*. This module adds the two
instruments R1 specifies.

1. A unified **action-class classifier** over executed cognition functions, using
   the seven classes the audit proposes (reflex / regulatory / orienting /
   communicative / productive / maintenance / failed-blocked). It reuses the
   selection-time outward-presence tiers (`_OUTWARD_HIGH/MED/LOW`) as the starting
   partition, as the audit recommends, and layers the remaining classes on top.

2. A **deferred follow-through audit**. When `behavioral_adaptation` arms a
   corrective, we snapshot the originating signal and the *expected* action class.
   K cycles later we answer the audit's two questions and write the answer back
   into the behavior_changes record as an `outcome`:
     • did the expected action class **rise** in the K-cycle window (vs the K
       cycles before)?
     • did the originating signal **fall**?  — the "relief test".

The difference between "the corrective was armed" and "the corrective worked"
(audit §1.4). State (`_window`, `_pending`) is per-process and best-effort: a
restart simply leaves any in-flight record `pending` and resumes auditing fresh —
telemetry must never perturb the cognitive loop.
"""
from __future__ import annotations

import threading
import uuid
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from brain.utils.json_utils import load_json, modify_json
from brain.paths import DATA_DIR, SIGNAL_STATE_FILE
from brain.utils.get_cycle_count import get_cycle_count
from brain.utils.log import log_private

# Reuse the selection-time outward tiers as the starting partition (audit §1.4).
from brain.think.think_utils.selection.tag_sets import (
    _OUTWARD_HIGH, _OUTWARD_MED, _OUTWARD_LOW,
)

_CHANGE_LOG_PATH = DATA_DIR / "behavior_changes.json"

# ── The seven action classes (audit §1.4 taxonomy) ──────────────────────────
REFLEX = "reflex"
REGULATORY = "regulatory"
ORIENTING = "orienting"
COMMUNICATIVE = "communicative"
PRODUCTIVE = "productive"
MAINTENANCE = "maintenance"
FAILED_BLOCKED = "failed_blocked"

# Classes not cleanly covered by the outward tiers, listed explicitly. Communicative
# is checked before the outward tiers because notify_user/announce_to_dashboard sit
# in _OUTWARD_HIGH but are speech acts, not produced artifacts.
_COMMUNICATIVE = frozenset({
    "speak", "express_to_user", "express_state", "respond_to_user",
    "notify_user", "announce_to_dashboard", "ask_user", "greet_user",
})
_REFLEX = frozenset({"threat_response", "fight_flight", "freeze_response", "startle"})
_REGULATORY = frozenset({
    "attempt_regulation", "self_soothing", "emotional_regulation",
    "idle_consolidation_cycle", "reflect_on_affect",
    "investigate_unexplained_emotions", "check_affect_drift",
})
_MAINTENANCE = frozenset({
    "metacog_flush", "self_review", "narrative_update", "reflection",
    "reflect_on_directive", "detect_memory_contradictions",
    "consolidate_memory", "propose_value_revision",
})


def classify_action(fn_name: str, *, blocked: bool = False) -> str:
    """Map an executed cognition function to one of the seven action classes.

    `blocked=True` (the executor reported the action failed/blocked) overrides to
    failed_blocked — a reflex that can't fire is not regulation. Unknown internal
    functions default to maintenance (housekeeping), never to a productive class,
    so the audit never over-credits follow-through."""
    if blocked:
        return FAILED_BLOCKED
    n = (fn_name or "").strip()
    if not n:
        return MAINTENANCE
    if n in _REFLEX:
        return REFLEX
    if n in _COMMUNICATIVE:
        return COMMUNICATIVE
    if n in _OUTWARD_HIGH:          # outward_artifact tier → produced something
        return PRODUCTIVE
    if n in _OUTWARD_MED or n in _OUTWARD_LOW:  # explore / sense the world
        return ORIENTING
    if n in _REGULATORY:
        return REGULATORY
    return MAINTENANCE


# ── Follow-through audit state (per-process, thread-safe) ────────────────────
_K_CYCLES = 8                    # window over which follow-through is measured
_WINDOW_MAX = 256                # rolling (cycle, action_class) history
_lock = threading.Lock()
_window: Deque[Tuple[int, str]] = deque(maxlen=_WINDOW_MAX)
_pending: List[Dict[str, Any]] = []

# pattern (behavioral_adaptation type) → (expected action class, relief signal).
# The relief signal is a core_signals scalar that SHOULD fall once the corrective
# lands. impasse_signal is the canonical "internal pressure / stuckness" scalar, so
# it serves every stuck-pattern; emotional_stagnation relieves on low_affect_signal.
_PATTERN_AUDIT: Dict[str, Tuple[str, str]] = {
    "goal_avoidance":       (PRODUCTIVE, "impasse_signal"),
    "reflection_imbalance": (PRODUCTIVE, "impasse_signal"),
    "rut":                  (ORIENTING,  "impasse_signal"),
    "oscillation":          (ORIENTING,  "impasse_signal"),
    "emotional_stagnation": (ORIENTING,  "low_affect_signal"),
}


def new_audit_id() -> str:
    return uuid.uuid4().hex[:12]


def _read_signal(key: str) -> Optional[float]:
    try:
        cs = (load_json(SIGNAL_STATE_FILE, default_type=dict) or {}).get("core_signals") or {}
        v = cs.get(key)
        return float(v) if v is not None else None
    except Exception:
        return None  # intentional: best-effort telemetry read — a missing/locked signal file just yields "no reading", never breaks the audit


def note_armed(audit_id: str, pattern: str, *, cycle: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Register a just-armed corrective for follow-through. Snapshots the
    originating signal value + expected class so the relief test can be measured K
    cycles later. Returns the `outcome` stub to stamp on the behavior_changes
    record (status="pending"), or None for an unaudited pattern type."""
    spec = _PATTERN_AUDIT.get(pattern)
    if spec is None:
        return None
    expected_class, signal_key = spec
    try:
        c = int(cycle if cycle is not None else get_cycle_count())
    except Exception:
        c = 0
    sig0 = _read_signal(signal_key)
    with _lock:
        _pending.append({
            "id": audit_id, "arm_cycle": c, "signal_key": signal_key,
            "signal_at_arm": sig0, "expected_class": expected_class,
            "pattern": pattern, "k": _K_CYCLES,
        })
    return {
        "status": "pending", "k": _K_CYCLES, "expected_class": expected_class,
        "signal": signal_key, "signal_at_arm": sig0, "arm_cycle": c,
    }


def tick(context: Optional[Dict[str, Any]], fn_name: str, *, blocked: bool = False) -> None:
    """Per-cycle hook (from finalize_cycle): record this cycle's action class and
    resolve any pending audit whose K-cycle window has now elapsed. Best-effort."""
    try:
        c = int(get_cycle_count())
    except Exception:
        return  # intentional: no cycle clock → skip this tick; the audit is best-effort and must never perturb finalize
    cls = classify_action(fn_name, blocked=blocked)
    with _lock:
        _window.append((c, cls))
        ready = [p for p in _pending if c >= p["arm_cycle"] + p["k"]]
        for p in ready:
            _pending.remove(p)
    for p in ready:
        try:
            _resolve(p)
        except Exception as e:
            log_private(f"[signal_action_audit] resolve failed: {e}")


def _class_count(lo: int, hi: int, cls: str) -> int:
    """Count expected-class firings in cycles (lo, hi]. Reads the shared window."""
    with _lock:
        return sum(1 for (cyc, c) in _window if lo < cyc <= hi and c == cls)


def _resolve(p: Dict[str, Any]) -> None:
    """Compute the follow-through outcome for one armed corrective and write it
    back into its behavior_changes record."""
    arm, k, cls = p["arm_cycle"], p["k"], p["expected_class"]
    after = _class_count(arm, arm + k, cls)            # expected class in the window
    before = _class_count(arm - k, arm, cls)           # …vs the K cycles before arming
    sig_now = _read_signal(p["signal_key"])
    sig0 = p.get("signal_at_arm")
    delta = round(sig_now - sig0, 4) if (sig_now is not None and sig0 is not None) else None
    relieved = (delta is not None and delta < 0.0)
    rose = after > before
    outcome = {
        "status": "resolved",
        "expected_class": cls,
        "expected_class_before": before,
        "expected_class_after": after,
        "expected_class_rose": rose,
        "signal": p["signal_key"],
        "signal_delta": delta,
        "relieved": relieved,
        # "landed" = the corrective both produced the right action class AND the
        # originating signal relaxed (or we couldn't read the signal but the class
        # rose). This is the audit's actual success criterion, not "was armed".
        "landed": bool(rose and (relieved or delta is None)),
        "k": k,
    }
    _write_outcome(p["id"], outcome)


def _write_outcome(audit_id: str, outcome: Dict[str, Any]) -> None:
    try:
        with modify_json(_CHANGE_LOG_PATH, list) as log:
            for rec in log:
                if isinstance(rec, dict) and rec.get("_audit_id") == audit_id:
                    rec["outcome"] = outcome
                    break
    except Exception as e:
        log_private(f"[signal_action_audit] outcome write failed: {e}")


def audit_summary(n: int = 120) -> Dict[str, Any]:
    """Aggregate read over the recent resolved records: per-pattern landed/relief
    rates — the 'did the signal→action chain follow through?' rollup. Pure read."""
    recs = [r for r in (load_json(_CHANGE_LOG_PATH, default_type=list) or [])
            if isinstance(r, dict)][-max(1, n):]
    by_pattern: Dict[str, Dict[str, int]] = {}
    resolved = landed = relieved = 0
    for r in recs:
        oc = r.get("outcome") or {}
        if oc.get("status") != "resolved":
            continue
        resolved += 1
        pat = str(r.get("pattern") or "?")
        b = by_pattern.setdefault(pat, {"resolved": 0, "landed": 0, "relieved": 0})
        b["resolved"] += 1
        if oc.get("landed"):
            landed += 1
            b["landed"] += 1
        if oc.get("relieved"):
            relieved += 1
            b["relieved"] += 1
    return {
        "resolved": resolved,
        "landed": landed,
        "relieved": relieved,
        "landed_rate": round(landed / resolved, 3) if resolved else None,
        "relief_rate": round(relieved / resolved, 3) if resolved else None,
        "by_pattern": by_pattern,
        "pending": len(_pending),
    }
